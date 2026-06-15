"""
Blast Radius Predictor — predicts FUTURE service failures 3-5 minutes early.

BFS over the causal graph, propagating impact probability with decay.
Returns services ranked by impact probability and predicted ETA.
"""
import logging
from typing import List, Optional, Dict, Any
from collections import deque

logger = logging.getLogger(__name__)


class BlastRadiusPredictor:
    """
    Predicts downstream service impact before failures materialize.

    Algorithm:
    1. Start at the root cause node in the causal graph
    2. BFS outward over causal edges
    3. At each hop, multiply probability by edge strength and depth decay
    4. Filter services below impact threshold
    5. Estimate ETA based on hop depth × propagation_delay_minutes
    """

    def __init__(
        self,
        impact_threshold: float = 0.15,
        propagation_delay_minutes: float = 3.0,
        depth_decay: float = 0.85,
    ):
        self.impact_threshold = impact_threshold
        self.propagation_delay_minutes = propagation_delay_minutes
        self.depth_decay = depth_decay

    def predict(
        self,
        root_cause: str,
        graph: dict,
        current_metrics: Optional[dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        Predict blast radius from a root cause node.

        Args:
            root_cause:       Node ID of the identified root cause.
            graph:            {"nodes": [...], "edges": [{source, target, strength}]}
            current_metrics:  Optional dict of service → current metric values
                              used to boost probability for already-degrading services.

        Returns:
            List of affected services sorted by impact_probability desc:
            [
              {
                "service": "payment-service",
                "impact_probability": 0.71,
                "eta_minutes": 3,
                "priority": "high",
                "propagation_path": ["db-primary", "api-gateway", "payment-service"],
              },
              ...
            ]
        """
        # Build adjacency map
        adj: Dict[str, List[Dict]] = {}
        for edge in graph.get("edges", []):
            src = edge["source"]
            adj.setdefault(src, []).append(edge)

        at_risk: List[Dict[str, Any]] = []
        visited: Dict[str, float] = {root_cause: 1.0}
        queue: deque = deque([(root_cause, 0, 1.0, [root_cause])])

        while queue:
            node, depth, prob, path = queue.popleft()

            downstream = [
                e for e in adj.get(node, [])
                if e["target"] not in visited or visited[e["target"]] < prob * e["strength"]
            ]

            for edge in downstream:
                tgt = edge["target"]
                edge_strength = float(edge.get("strength", 0.5))

                # Impact decay: probability × edge_strength × depth_decay^depth
                impact = prob * edge_strength * (self.depth_decay ** depth)

                # Boost if service is already showing degradation
                if current_metrics and tgt in current_metrics:
                    degradation = self._measure_degradation(current_metrics[tgt])
                    impact = min(1.0, impact * (1.0 + degradation))

                if impact < self.impact_threshold:
                    continue

                visited[tgt] = impact
                eta = round((depth + 1) * self.propagation_delay_minutes, 1)
                new_path = path + [tgt]

                at_risk.append({
                    "service": tgt,
                    "impact_probability": round(impact, 3),
                    "eta_minutes": eta,
                    "priority": self._classify_priority(impact),
                    "propagation_path": new_path,
                    "hop_depth": depth + 1,
                })

                queue.append((tgt, depth + 1, impact, new_path))

        # Deduplicate — keep highest impact per service
        seen: Dict[str, Dict] = {}
        for item in at_risk:
            svc = item["service"]
            if svc not in seen or item["impact_probability"] > seen[svc]["impact_probability"]:
                seen[svc] = item

        return sorted(seen.values(), key=lambda x: x["impact_probability"], reverse=True)

    def _classify_priority(self, probability: float) -> str:
        if probability >= 0.7:
            return "critical"
        if probability >= 0.4:
            return "high"
        if probability >= 0.2:
            return "medium"
        return "low"

    def _measure_degradation(self, metrics: dict) -> float:
        """
        Compute a 0-1 degradation score for a service's current metrics.
        Higher = more degraded = boost the blast radius probability.
        """
        score = 0.0
        if "error_rate" in metrics:
            er = metrics["error_rate"]
            if isinstance(er, list):
                er = er[-1] if er else 0
            score += min(1.0, er / 10.0) * 0.5

        if "response_time" in metrics:
            rt = metrics["response_time"]
            if isinstance(rt, list):
                rt = rt[-1] if rt else 0
            score += min(1.0, rt / 1000.0) * 0.5

        return min(1.0, score)

    def format_for_frontend(self, blast_radius: List[Dict]) -> List[Dict]:
        """
        Format blast radius results for the React frontend.
        Matches the BlastRadius store type.
        """
        return [
            {
                "service": item["service"],
                "probability": item["impact_probability"],
                "eta_minutes": item["eta_minutes"],
                "priority": item["priority"],
                "propagation_path": item.get("propagation_path", []),
            }
            for item in blast_radius
        ]


# Satisfy Optional import in blast_radius.py  
from typing import Optional
