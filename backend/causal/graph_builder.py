"""
Causal Graph Builder — auto-discovers causal structure from Splunk metric time-series.

Uses the PC (Peter-Clark) algorithm from causal-learn to discover directed causal
edges purely from observational data, then merges the result with the known service
topology sourced from Splunk's ``service_deps`` lookup.

Robustness notes:
  • Columns with zero variance are dropped before the PC algorithm runs.
    numpy's ``corrcoef`` divides by std; passing a constant column produces
    ``RuntimeWarning: invalid value encountered in divide`` — we prevent that.
  • If causal-learn is unavailable or the PC algorithm fails, we fall back to
    Granger-style lag correlations (not true causal inference, clearly labelled).
"""
from __future__ import annotations

import logging
import warnings
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CausalGraphBuilder:
    """
    Builds a causal graph by combining:
      1. Data-driven discovery via the PC algorithm (causal-learn)
      2. Known service topology from Splunk ``service_deps`` lookup
    """

    # ── Public API ─────────────────────────────────────────────────────────

    def build_from_metrics(
        self,
        metrics_df: pd.DataFrame,
        known_deps: Optional[list] = None,
        alpha:      float = 0.05,
    ) -> dict:
        """
        Auto-discover causal edges from a multivariate metric DataFrame.

        Parameters
        ----------
        metrics_df:
            Wide DataFrame — each column is one metric time-series
            (e.g. ``db_query_latency``, ``api_error_rate``).
        known_deps:
            List of ``(source, target)`` tuples from the Splunk topology
            lookup.  These are merged in with full trust (``strength=1.0``).
        alpha:
            Significance level for the PC algorithm's conditional independence
            tests.

        Returns
        -------
        dict
            ``{"nodes": [...], "edges": [{source, target, strength, discovered, p_value}]}``
        """
        known_deps    = known_deps or []
        all_nodes     = list(metrics_df.columns)
        disc_edges:  list[dict] = []

        # ── Remove constant / near-constant columns ────────────────────────
        # These cause division-by-zero in Fisher's Z and numpy corrcoef.
        stds        = metrics_df.std(axis=0)
        valid_cols  = [c for c in all_nodes if stds[c] > 1e-9]
        dropped     = set(all_nodes) - set(valid_cols)
        if dropped:
            logger.debug(
                "Dropped %d near-constant column(s) before PC algorithm: %s",
                len(dropped), dropped,
            )
        clean_df = metrics_df[valid_cols].fillna(0)

        if len(valid_cols) < 2:
            logger.warning(
                "Fewer than 2 variable columns after degenerate-column removal — "
                "skipping PC algorithm, using topology only."
            )
        else:
            disc_edges = self._run_pc(clean_df, valid_cols, alpha)

        # ── Merge topology edges ───────────────────────────────────────────
        existing = {(e["source"], e["target"]) for e in disc_edges}
        for src, tgt in known_deps:
            if src in all_nodes and tgt in all_nodes:
                key = (src, tgt)
                if key not in existing:
                    disc_edges.append({
                        "source":     src,
                        "target":     tgt,
                        "strength":   1.0,
                        "discovered": False,
                        "p_value":    None,
                    })
                    existing.add(key)

        return {"nodes": all_nodes, "edges": disc_edges}

    def build_from_topology(self, topology_results: list[dict]) -> dict:
        """
        Build a causal graph from Splunk topology search results alone.
        Used when metric data is insufficient for statistical discovery.

        Each row should have ``host`` and ``depends_on`` keys.
        ``depends_on → host`` is the causal direction (dependency causes the
        dependent service to be affected).
        """
        nodes: set[str] = set()
        edges: list[dict] = []
        for row in topology_results:
            src = row.get("host", "")
            tgt = row.get("depends_on", "")
            if src and tgt:
                nodes.update({src, tgt})
                edges.append({
                    "source":     tgt,   # dependency is the cause
                    "target":     src,
                    "strength":   1.0,
                    "discovered": False,
                    "p_value":    None,
                })
        return {"nodes": list(nodes), "edges": edges}

    def merge_graphs(self, discovered: dict, topology: dict) -> dict:
        """
        Merge a data-discovered graph with a topology-based graph.
        Topology edges take precedence when both graphs share an edge.
        """
        all_nodes = list(set(discovered["nodes"] + topology["nodes"]))
        edge_map: dict[tuple, dict] = {}
        for e in discovered["edges"]:
            edge_map[(e["source"], e["target"])] = e
        for e in topology["edges"]:
            edge_map[(e["source"], e["target"])] = e   # topology wins
        return {"nodes": all_nodes, "edges": list(edge_map.values())}

    # ── PC algorithm ──────────────────────────────────────────────────────

    def _run_pc(
        self,
        df:     pd.DataFrame,
        nodes:  list[str],
        alpha:  float,
    ) -> list[dict]:
        """
        Run causal-learn's PC algorithm on ``df``.

        Returns a list of directed edge dicts.  Falls back to
        ``_lag_correlation_edges`` on any failure.
        """
        try:
            from causallearn.search.ConstraintBased.PC import pc   # type: ignore

            data = df.values.astype(float)

            # Z-score standardise — safe because we already dropped zero-std cols
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                means = data.mean(axis=0)
                stds  = data.std(axis=0)
                stds[stds < 1e-9] = 1.0   # belt-and-suspenders guard
                data_std = (data - means) / stds

            cg = pc(data_std, alpha=alpha, indep_test="fisherz")

            edges: list[dict] = []
            n = len(nodes)
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    # cg.G.graph[i, j] == -1  AND  cg.G.graph[j, i] == 1
                    # means there is a directed edge i → j
                    if cg.G.graph[i, j] == -1 and cg.G.graph[j, i] == 1:
                        raw_strength = float(abs(cg.G.graph[i, j]))
                        edges.append({
                            "source":     nodes[i],
                            "target":     nodes[j],
                            "strength":   round(min(raw_strength, 1.0), 3),
                            "discovered": True,
                            "p_value":    round(alpha, 4),
                        })

            logger.info("PC algorithm discovered %d causal edge(s)", len(edges))
            return edges

        except ImportError:
            logger.warning(
                "causal-learn not installed — falling back to lag-correlation edges"
            )
            return self._lag_correlation_edges(df)
        except Exception as exc:
            logger.warning(
                "PC algorithm raised an exception (%s) — falling back to "
                "lag-correlation edges", exc,
            )
            return self._lag_correlation_edges(df)

    # ── Lag-correlation fallback ───────────────────────────────────────────

    def _lag_correlation_edges(self, df: pd.DataFrame) -> list[dict]:
        """
        Approximate directed edges via 1-step Granger-like lag correlations.

        For each ordered pair (i, j) with |corr(x_i[t], x_j[t+1])| > 0.6
        we infer a potential causal edge i → j.

        This is NOT true causal inference and is clearly labelled as
        ``discovered=True`` with a note that it is a correlation proxy.
        Only used when causal-learn is absent or fails.
        """
        cols = list(df.columns)
        data = df.fillna(0)
        edges: list[dict] = []

        for i, col_i in enumerate(cols):
            for j, col_j in enumerate(cols):
                if i == j:
                    continue
                x = data[col_i].values[:-1]
                y = data[col_j].values[1:]
                if x.std() < 1e-9 or y.std() < 1e-9:
                    continue
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", RuntimeWarning)
                        corr = float(np.corrcoef(x, y)[0, 1])
                    if np.isfinite(corr) and abs(corr) > 0.6:
                        edges.append({
                            "source":     col_i,
                            "target":     col_j,
                            "strength":   round(abs(corr), 3),
                            "discovered": True,
                            "p_value":    None,
                        })
                except Exception:
                    continue

        logger.debug("Lag-correlation fallback produced %d edge(s)", len(edges))
        return edges
