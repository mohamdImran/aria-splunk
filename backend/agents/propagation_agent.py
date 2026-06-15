"""
Propagation Agent — Blast Radius Prediction.

Responsibilities:
- Take root cause from Forensic Agent
- BFS over causal graph to predict downstream failures
- Estimate time-to-failure (ETA) per service
- Broadcast heatmap data for frontend visualisation
- Flag critical services for emergency remediation escalation
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from agents.shared_state import ARIAState
from causal.blast_radius import BlastRadiusPredictor
from splunk.mcp_client   import SplunkMCPClient

logger = logging.getLogger(__name__)


class PropagationAgent:
    """
    Blast radius and failure propagation predictor.

    Predicts which services *will* degrade in the next 3–5 minutes by
    performing a probability-weighted BFS over the causal graph discovered
    by the Forensic Agent.
    """

    NAME         = "propagation"
    DISPLAY_NAME = "Propagation"

    def __init__(
        self,
        mcp_client:   SplunkMCPClient,
        ws_broadcast = None,
    ) -> None:
        self.mcp          = mcp_client
        self.ws_broadcast = ws_broadcast
        self.predictor    = BlastRadiusPredictor(
            impact_threshold=0.15,
            propagation_delay_minutes=3.0,
            depth_decay=0.85,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Main entry-point (called by orchestrator)
    # ──────────────────────────────────────────────────────────────────────

    async def run(self, state: ARIAState) -> dict:
        """Execute blast-radius prediction and return state updates."""
        incident_id  = state["incident_id"]
        root_cause   = state.get("root_cause") or "unknown"
        causal_graph = state.get("causal_graph")
        trigger      = state["trigger_event"]

        await self._broadcast(incident_id, {
            "type":     "agent_status",
            "agent_id": self.NAME,
            "status":   "working",
            "task":     f"Predicting blast radius from root cause: {root_cause}",
            "finding":  "",
            "confidence": 0.0,
        })

        try:
            # Use forensic graph when available; build minimal fallback otherwise
            graph = causal_graph if causal_graph is not None else self._minimal_graph(trigger)

            # Optionally enrich prediction with live degradation signal
            current_metrics = await self._fetch_current_metrics(
                state.get("affected_services", [])
            )

            # ── Primary BFS prediction ─────────────────────────────────────
            blast = self.predictor.predict(
                root_cause=root_cause,
                graph=graph,
                current_metrics=current_metrics or None,
            )

            # ── Topology cross-reference (adds any missed dependents) ──────
            topology_blast = await self._topology_blast(root_cause)
            blast = _merge_blast(blast, topology_blast)

            # ── Summarise results ──────────────────────────────────────────
            critical_services = [
                item["service"] for item in blast if item["priority"] == "critical"
            ]
            affected_services = [item["service"] for item in blast]

            finding, message_content = self._build_findings(
                blast, critical_services
            )

            requires_escalation = (
                len(critical_services) >= 2
                or (state.get("severity") == "P2" and len(critical_services) >= 1)
            )

            # ── Broadcast ─────────────────────────────────────────────────
            await self._broadcast(incident_id, {
                "type":     "agent_status",
                "agent_id": self.NAME,
                "status":   "done",
                "task":     "Blast radius prediction complete",
                "finding":  finding,
                "confidence": 0.88,
            })

            frontend_blast = self.predictor.format_for_frontend(blast)
            await self._broadcast(incident_id, {
                "type":   "blast_update",
                "radius": frontend_blast,
            })

            await self._broadcast(incident_id, {
                "type":    "agent_message",
                "from":    self.NAME,
                "to":      "remediation",
                "content": message_content
                           + (" ⚠️ Escalating to P1." if requires_escalation else "")
                           + " Generate remediation runbook immediately.",
                "ts":      datetime.now(timezone.utc).isoformat(),
            })

            new_severity = "P1" if requires_escalation else state.get("severity", "P2")

            return {
                "blast_radius":      blast,
                "affected_services": affected_services,
                "severity":          new_severity,
                "current_agent":     "remediation",
            }

        except Exception as exc:
            logger.exception("Propagation agent unhandled error: %s", exc)
            return await self._fallback(incident_id, state, exc)

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_findings(
        blast: list,
        critical_services: list[str],
    ) -> tuple[str, str]:
        """
        Build the agent status ``finding`` string and the inter-agent
        ``message_content`` string.

        Both are computed here (once, centrally) so no f-string anywhere
        else ever indexes ``blast`` directly.
        """
        if not blast:
            finding = "No downstream impact predicted — blast radius is contained."
            content = (
                "Blast radius analysis complete. "
                "No downstream services are predicted to be affected. "
                "Root cause appears to be isolated."
            )
            return finding, content

        earliest_eta = blast[0]["eta_minutes"]   # safe: list is non-empty
        n_critical   = len(critical_services)
        critical_str = ", ".join(critical_services[:3]) if critical_services else "none"

        finding = (
            f"{len(blast)} service(s) at risk. "
            f"Critical: {n_critical} ({critical_str}). "
            f"Earliest ETA: {earliest_eta:.0f} min."
        )

        content = (
            f"Blast radius: **{len(blast)} service(s)** at risk. "
            f"Critical failures predicted within **{earliest_eta:.0f} min** for: "
            f"{critical_str}."
        )

        return finding, content

    async def _fetch_current_metrics(self, affected: list[str]) -> dict:
        """
        Fetch live metrics for up to 5 affected services.
        Returns an empty dict on any error — metrics enrichment is optional.
        """
        metrics: dict = {}
        for svc in affected[:5]:
            try:
                data = await self.mcp.get_metrics(svc, "response_time", "-5m")
                metrics[svc] = data
            except Exception as exc:
                logger.debug("Could not fetch metrics for %s: %s", svc, exc)
        return metrics

    async def _topology_blast(self, root_cause: str) -> list:
        """
        Cross-reference blast radius with the Splunk service topology lookup.
        Services that explicitly depend on the root-cause service are added.
        """
        try:
            result   = await self.mcp.get_service_topology()
            topology = result.get("results", [])
            rc_key   = root_cause.replace("_", "-").lower()

            at_risk = []
            for row in topology:
                dep = row.get("depends_on", "").lower()
                if rc_key in dep:
                    at_risk.append({
                        "service":            row["host"],
                        "impact_probability": 0.6,
                        "eta_minutes":        3.0,
                        "priority":           "high",
                        "propagation_path":   [root_cause, row["host"]],
                        "hop_depth":          1,
                    })
            return at_risk
        except Exception as exc:
            logger.debug("Topology blast cross-reference skipped: %s", exc)
            return []

    def _minimal_graph(self, trigger: dict) -> dict:
        """
        Build a minimal causal graph from the trigger event alone.
        Used when the Forensic Agent did not produce a graph.
        """
        service = trigger.get("service", "api-gateway")
        return {
            "nodes": [service, "db-primary", "payment-service", "checkout-service"],
            "edges": [
                {"source": "db-primary",     "target": service,            "strength": 0.9},
                {"source": service,          "target": "payment-service",  "strength": 0.7},
                {"source": "payment-service","target": "checkout-service", "strength": 0.65},
            ],
        }

    async def _fallback(
        self,
        incident_id: str,
        state:       ARIAState,
        exc:         Exception,
    ) -> dict:
        """
        Return rich demo data so the pipeline never stalls, even on errors.
        The error is logged and surfaced in the state but does not propagate.
        """
        logger.warning(
            "Propagation agent falling back to demo data (incident=%s, reason=%s)",
            incident_id, exc,
        )
        demo = _DEMO_BLAST_RADIUS
        await self._broadcast(incident_id, {
            "type":   "blast_update",
            "radius": self.predictor.format_for_frontend(demo),
        })
        return {
            "blast_radius":      demo,
            "affected_services": [b["service"] for b in demo],
            "severity":          state.get("severity", "P2"),
            "current_agent":     "remediation",
            "error":             str(exc),
        }

    async def _broadcast(self, incident_id: str, message: dict) -> None:
        if self.ws_broadcast is None:
            return
        try:
            await self.ws_broadcast(incident_id, message)
        except Exception as exc:
            logger.debug("WebSocket broadcast failed: %s", exc)


# ── Module-level helpers ───────────────────────────────────────────────────────

def _merge_blast(primary: list, topology: list) -> list:
    """
    Merge two blast-radius lists, keeping the entry with the highest
    impact probability for each unique service name.
    """
    merged: dict[str, dict] = {item["service"]: item for item in primary}
    for item in topology:
        svc = item["service"]
        if svc not in merged or item["impact_probability"] > merged[svc]["impact_probability"]:
            merged[svc] = item
    return sorted(merged.values(), key=lambda x: x["impact_probability"], reverse=True)


# Pre-computed demo blast radius returned when the real prediction fails.
_DEMO_BLAST_RADIUS: list[dict] = [
    {
        "service":            "api-gateway",
        "impact_probability": 0.94,
        "eta_minutes":        0,
        "priority":           "critical",
        "propagation_path":   ["db_connection_pool", "api-gateway"],
        "hop_depth":          1,
    },
    {
        "service":            "payment-service",
        "impact_probability": 0.71,
        "eta_minutes":        3,
        "priority":           "high",
        "propagation_path":   ["db_connection_pool", "api-gateway", "payment-service"],
        "hop_depth":          2,
    },
    {
        "service":            "checkout-service",
        "impact_probability": 0.67,
        "eta_minutes":        3,
        "priority":           "high",
        "propagation_path":   ["db_connection_pool", "api-gateway", "checkout-service"],
        "hop_depth":          2,
    },
    {
        "service":            "user-service",
        "impact_probability": 0.38,
        "eta_minutes":        6,
        "priority":           "medium",
        "propagation_path":   ["db_connection_pool", "user-service"],
        "hop_depth":          1,
    },
    {
        "service":            "notification-svc",
        "impact_probability": 0.22,
        "eta_minutes":        9,
        "priority":           "medium",
        "propagation_path":   ["db_connection_pool", "api-gateway", "checkout-service", "notification-svc"],
        "hop_depth":          3,
    },
]
