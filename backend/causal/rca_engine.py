"""
THE KEY DIFFERENTIATOR: True Causal Root Cause Analysis.

Instead of: "DB latency and API errors are correlated (r=0.91)"
ARIA says:   "DB connection pool caused API errors with 94% confidence.
              Counterfactual: without DB exhaustion, error rate would
              be 0.2% not 14.7%"

Uses DoWhy for causal graph estimation and counterfactual analysis.
Uses causal-learn PC algorithm for auto-discovering causal structure.

DoWhy API note (≥ 0.9):
  CausalModel requires both `treatment` and `outcome` at construction time.
  Both must be column names present in the data DataFrame.
"""
from __future__ import annotations

import logging
import warnings
from typing import Optional

import numpy as np
import pandas as pd

from causal.graph_builder   import CausalGraphBuilder
from causal.counterfactual  import CounterfactualAnalyzer
from causal.blast_radius    import BlastRadiusPredictor

logger = logging.getLogger(__name__)


class CausalRCAEngine:
    """
    Full causal root cause analysis engine.

    Pipeline:
        1. build_causal_graph()   — PC algorithm + topology merge
        2. analyze_root_cause()   — DoWhy causal estimation + chain tracing
        3. predict_blast_radius() — BFS impact propagation
    """

    def __init__(self) -> None:
        self.graph_builder  = CausalGraphBuilder()
        self.cf_analyzer    = CounterfactualAnalyzer()
        self.blast_predictor = BlastRadiusPredictor()

    # ── Public interface ───────────────────────────────────────────────────

    def build_causal_graph(
        self,
        metrics_df: pd.DataFrame,
        known_deps: Optional[list] = None,
    ) -> dict:
        """
        Auto-discover causal graph from Splunk metric time-series.
        Merges PC-discovered edges with known service topology.

        Returns ``{"nodes": [...], "edges": [{source, target, strength, discovered}]}``
        """
        return self.graph_builder.build_from_metrics(
            metrics_df,
            known_deps=known_deps or [],
        )

    def analyze_root_cause(
        self,
        incident_metric: str,
        df: pd.DataFrame,
        graph: dict,
    ) -> dict:
        """
        Full causal RCA returning root cause, causal chain, and counterfactuals.

        Example return value::

            {
                "root_cause":   "db_connection_pool",
                "confidence":   0.94,
                "causal_chain": [
                    {"cause": "db_connection_pool", "effect": "db_query_latency",  "strength": 0.89},
                    {"cause": "db_query_latency",   "effect": "api_response_time", "strength": 0.94},
                    {"cause": "api_response_time",  "effect": "checkout_errors",   "strength": 0.97},
                ],
                "counterfactuals": [...],
            }
        """
        causal_model = None
        confidence   = 0.0

        # Identify the best treatment variable before attempting DoWhy
        treatment = self._find_best_treatment(graph, incident_metric, df)

        # ── Step 1: DoWhy causal estimation ────────────────────────────────
        if (
            treatment
            and treatment in df.columns
            and incident_metric in df.columns
            and len(df) >= 5
            and df[treatment].std() > 1e-9
            and df[incident_metric].std() > 1e-9
        ):
            causal_model, confidence = self._run_dowhy(
                df, graph, treatment, incident_metric
            )

        # ── Step 2: Trace causal chain via BFS over the graph ──────────────
        root_cause  = self._find_root_cause(graph, incident_metric, df)
        causal_chain = self._trace_causal_chain(graph, root_cause, incident_metric)

        # ── Step 3: Fallback confidence from Pearson correlation ───────────
        if confidence < 0.01:
            confidence = self._statistical_confidence(root_cause, incident_metric, df)

        # ── Step 4: Counterfactual scenarios ───────────────────────────────
        counterfactuals = self.cf_analyzer.generate(
            model=causal_model,
            root_cause=root_cause,
            outcome=incident_metric,
            df=df,
            graph=graph,
        )

        return {
            "root_cause":      root_cause,
            "confidence":      round(max(0.01, min(0.99, confidence)), 3),
            "causal_chain":    causal_chain,
            "counterfactuals": counterfactuals,
        }

    def predict_blast_radius(
        self,
        root_cause: str,
        graph: dict,
        metrics: Optional[dict] = None,
    ) -> list:
        """BFS over causal graph → ranked list of at-risk services with ETAs."""
        return self.blast_predictor.predict(root_cause, graph, metrics)

    # ── DoWhy integration ──────────────────────────────────────────────────

    def _run_dowhy(
        self,
        df: pd.DataFrame,
        graph: dict,
        treatment: str,
        outcome: str,
    ) -> tuple[object | None, float]:
        """
        Attempt DoWhy causal effect estimation.

        Returns ``(CausalModel | None, confidence_float)``.
        Handles the DoWhy ≥ 0.9 API requirement that both ``treatment``
        and ``outcome`` are passed to the constructor.
        """
        try:
            from dowhy import CausalModel  # type: ignore

            gml   = self._graph_to_gml(graph, df.columns.tolist(), treatment, outcome)
            clean = df[[c for c in df.columns if df[c].std() > 1e-9]].fillna(0)

            if treatment not in clean.columns or outcome not in clean.columns:
                return None, 0.0

            # DoWhy ≥ 0.9 requires treatment and outcome at construction
            model = CausalModel(
                data=clean,
                treatment=treatment,
                outcome=outcome,
                graph=gml,
            )

            estimand = model.identify_effect(proceed_when_unidentifiable=True)

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                estimate = model.estimate_effect(
                    estimand,
                    method_name="backdoor.linear_regression",
                    treatment_value=float(clean[treatment].quantile(0.9)),
                    control_value=float(clean[treatment].quantile(0.1)),
                )

            confidence = float(min(0.99, abs(estimate.value)))
            logger.info(
                "DoWhy estimate — treatment=%s outcome=%s confidence=%.3f",
                treatment, outcome, confidence,
            )
            return model, confidence

        except ImportError:
            logger.info("DoWhy not installed — using statistical confidence fallback")
            return None, 0.0
        except Exception as exc:
            logger.warning("DoWhy estimation failed: %s", exc)
            return None, 0.0

    # ── Internal graph traversal ───────────────────────────────────────────

    def _find_root_cause(
        self,
        graph: dict,
        incident_metric: str,
        df: pd.DataFrame,
    ) -> str:
        """
        Score every ancestor node by anomaly magnitude + causal path strength
        + source-node bonus (nodes with no parents are more likely true roots).
        """
        ancestors = self._get_ancestors(graph, incident_metric)
        if not ancestors:
            return incident_metric

        scores: dict[str, float] = {}
        for node in ancestors:
            anomaly   = self._anomaly_score(node, df)
            strength  = self._path_strength(graph, node, incident_metric)
            is_source = not any(e["target"] == node for e in graph["edges"])
            scores[node] = anomaly * 0.5 + strength * 0.3 + (0.2 if is_source else 0.0)

        best = max(scores, key=lambda n: scores[n])
        logger.info("Root cause identified: %s (score=%.3f)", best, scores[best])
        return best

    def _get_ancestors(self, graph: dict, node: str) -> list[str]:
        """Return all nodes that can reach ``node`` through directed edges."""
        reverse: dict[str, list[str]] = {}
        for e in graph["edges"]:
            reverse.setdefault(e["target"], []).append(e["source"])

        visited: set[str] = set()
        queue  = [node]
        result: list[str] = []
        while queue:
            current = queue.pop(0)
            for parent in reverse.get(current, []):
                if parent not in visited:
                    visited.add(parent)
                    result.append(parent)
                    queue.append(parent)
        return result

    def _trace_causal_chain(
        self,
        graph: dict,
        root: str,
        outcome: str,
    ) -> list[dict]:
        """BFS shortest path from ``root`` to ``outcome``, returned as edge list."""
        adj: dict[str, list[dict]] = {}
        for e in graph["edges"]:
            adj.setdefault(e["source"], []).append(e)

        edge_index: dict[tuple[str, str], dict] = {
            (e["source"], e["target"]): e for e in graph["edges"]
        }

        queue: list[list[str]] = [[root]]
        visited: set[str] = {root}

        while queue:
            path = queue.pop(0)
            node = path[-1]
            if node == outcome:
                return [
                    {
                        "cause":    path[i],
                        "effect":   path[i + 1],
                        "strength": round(
                            float(edge_index.get((path[i], path[i + 1]), {}).get("strength", 0.8)),
                            3,
                        ),
                    }
                    for i in range(len(path) - 1)
                ]
            for edge in adj.get(node, []):
                tgt = edge["target"]
                if tgt not in visited:
                    visited.add(tgt)
                    queue.append(path + [tgt])

        # No path found — return a direct single-hop edge
        return [{"cause": root, "effect": outcome, "strength": 0.8}]

    def _find_best_treatment(
        self,
        graph: dict,
        outcome: str,
        df: pd.DataFrame,
    ) -> Optional[str]:
        """
        Find the ancestor column with the highest absolute Pearson correlation
        to the outcome column.  Used as the DoWhy ``treatment`` variable.
        """
        ancestors = self._get_ancestors(graph, outcome)
        best_corr = 0.0
        best_node: Optional[str] = None

        for node in ancestors:
            if node not in df.columns or outcome not in df.columns:
                continue
            x = df[node].fillna(0).values
            y = df[outcome].fillna(0).values
            if x.std() < 1e-9 or y.std() < 1e-9:
                continue
            try:
                corr = float(abs(np.corrcoef(x, y)[0, 1]))
                if np.isfinite(corr) and corr > best_corr:
                    best_corr = corr
                    best_node = node
            except Exception:
                continue

        return best_node

    # ── Scoring helpers ────────────────────────────────────────────────────

    def _anomaly_score(self, node: str, df: pd.DataFrame) -> float:
        """Z-score-based anomaly magnitude (0–1) for a single metric column."""
        if node not in df.columns:
            return 0.5
        values = df[node].fillna(0).values
        if len(values) < 3:
            return 0.0
        std = float(values.std())
        if std < 1e-9:
            return 0.0
        z = np.abs((values - values.mean()) / std)
        return float(min(1.0, np.max(z) / 5.0))

    def _path_strength(self, graph: dict, src: str, tgt: str) -> float:
        """
        Product of edge strengths along the strongest path from ``src`` to ``tgt``.
        Traversed via a weighted BFS.
        """
        adj: dict[str, list[dict]] = {}
        for e in graph["edges"]:
            adj.setdefault(e["source"], []).append(e)

        best = 0.0
        queue: list[tuple[str, float]] = [(src, 1.0)]
        visited: set[str] = {src}

        while queue:
            node, strength = queue.pop(0)
            if node == tgt:
                best = max(best, strength)
                continue
            for edge in adj.get(node, []):
                nxt = edge["target"]
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, strength * float(edge.get("strength", 0.5))))

        return best

    def _statistical_confidence(
        self,
        cause: str,
        outcome: str,
        df: pd.DataFrame,
    ) -> float:
        """
        Pearson correlation as a confidence proxy when DoWhy is unavailable.
        Returns a value in [0, 1].
        """
        if cause not in df.columns or outcome not in df.columns:
            return 0.75
        x = df[cause].fillna(0).values
        y = df[outcome].fillna(0).values
        if x.std() < 1e-9 or y.std() < 1e-9:
            return 0.75
        try:
            corr = float(abs(np.corrcoef(x, y)[0, 1]))
            return round(corr, 3) if np.isfinite(corr) else 0.75
        except Exception:
            return 0.75

    # ── GML serialisation ──────────────────────────────────────────────────

    def _graph_to_gml(
        self,
        graph: dict,
        available_columns: list[str],
        treatment: str,
        outcome: str,
    ) -> str:
        """
        Convert the ARIA graph dict into a DoWhy-compatible GML string.

        Only nodes that exist as columns in the DataFrame are included,
        and node IDs are sanitised to valid identifiers.
        """
        col_set = set(available_columns)
        lines   = ["graph [", "  directed 1"]

        for node in graph["nodes"]:
            if node in col_set:
                safe = _safe_id(node)
                lines.append(f'  node [ id "{safe}" label "{safe}" ]')

        for edge in graph["edges"]:
            src, tgt = edge["source"], edge["target"]
            if src in col_set and tgt in col_set:
                lines.append(
                    f'  edge [ source "{_safe_id(src)}" target "{_safe_id(tgt)}" ]'
                )

        lines.append("]")
        return "\n".join(lines)


def _safe_id(name: str) -> str:
    """Sanitise a metric name into a valid GML node identifier."""
    return name.replace("-", "_").replace(" ", "_")
