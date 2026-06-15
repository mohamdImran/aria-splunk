"""
Sentinel Agent — Anomaly Detection.

Responsibilities:
- Monitor Splunk for anomalies via MCP tools
- Score anomaly severity across services
- Determine incident severity (P1-P4)
- Publish initial findings to ARIAState
- Broadcast agent_status updates over WebSocket
"""
import logging
import asyncio
from datetime import datetime
from typing import Optional

from agents.shared_state import ARIAState
from splunk.mcp_client import SplunkMCPClient
from splunk.spl_templates import SPLTemplates

logger = logging.getLogger(__name__)


class SentinelAgent:
    """
    Continuous anomaly monitor and initial incident classifier.
    First agent to run in the LangGraph pipeline.
    """

    NAME = "sentinel"
    DISPLAY_NAME = "Sentinel"

    def __init__(self, mcp_client: SplunkMCPClient, ws_broadcast=None):
        self.mcp = mcp_client
        self.ws_broadcast = ws_broadcast  # async callable(incident_id, message)

    async def run(self, state: ARIAState) -> dict:
        """
        LangGraph node function.
        Returns partial ARIAState updates (merged by LangGraph).
        """
        incident_id = state["incident_id"]
        trigger = state["trigger_event"]
        service = trigger.get("service", "unknown")

        await self._broadcast(incident_id, {
            "type": "agent_status",
            "agent_id": self.NAME,
            "status": "working",
            "task": f"Scanning {service} for anomalies via Splunk MCP",
            "finding": "",
            "confidence": 0.0,
        })

        try:
            anomalies = await self._detect_anomalies(service, trigger)
            severity = self._classify_severity(anomalies, trigger)
            affected = list({a["service"] for a in anomalies})

            finding = (
                f"Detected {len(anomalies)} anomalous signals across "
                f"{len(affected)} services. Severity: {severity}."
            )

            await self._broadcast(incident_id, {
                "type": "agent_status",
                "agent_id": self.NAME,
                "status": "done",
                "task": "Anomaly scan complete",
                "finding": finding,
                "confidence": 0.92,
            })

            await self._broadcast(incident_id, {
                "type": "agent_message",
                "from": self.NAME,
                "to": "forensic",
                "content": (
                    f"🔴 Anomaly confirmed on {service}. "
                    f"Found {len(anomalies)} signals. Severity={severity}. "
                    f"Handing off for causal analysis."
                ),
                "ts": datetime.utcnow().isoformat(),
            })

            return {
                "anomalies": anomalies,
                "affected_services": affected,
                "severity": severity,
                "current_agent": "forensic",
            }

        except Exception as e:
            logger.exception(f"Sentinel agent error: {e}")
            await self._broadcast(incident_id, {
                "type": "agent_status",
                "agent_id": self.NAME,
                "status": "error",
                "task": "Anomaly scan failed",
                "finding": str(e),
                "confidence": 0.0,
            })
            return {
                "anomalies": [self._fallback_anomaly(trigger)],
                "severity": trigger.get("severity", state["severity"]),
                "current_agent": "forensic",
                "error": str(e),
            }

    async def _detect_anomalies(self, service: str, trigger: dict) -> list:
        """Query Splunk for anomalous metrics using MCP tools."""
        anomalies = []

        # Primary anomaly from trigger event
        anomalies.append({
            "service": service,
            "metric": trigger.get("metric", "error_rate"),
            "value": trigger.get("value", 0.0),
            "threshold": trigger.get("threshold", 0.0),
            "severity": "high",
            "detected_at": datetime.utcnow().isoformat(),
            "method": "threshold_breach",
        })

        # Query Splunk for additional correlated anomalies
        try:
            result = await self.mcp.search(
                SPLTemplates.anomaly_detection(service),
                time_range="-30m",
            )
            splunk_anomalies = result.get("results", [])
            for row in splunk_anomalies[:10]:
                anomalies.append({
                    "service": service,
                    "metric": "response_time",
                    "value": float(row.get("rt", 0)),
                    "threshold": 500.0,
                    "severity": "medium",
                    "detected_at": row.get("_time", datetime.utcnow().isoformat()),
                    "method": "mltk_anomaly",
                })
        except Exception as e:
            logger.warning(f"Splunk anomaly query failed: {e}")

        # Check for error spikes via MCP
        try:
            spike_result = await self.mcp.search(
                SPLTemplates.error_spike(service),
                time_range="-15m",
            )
            for row in spike_result.get("results", [])[:5]:
                anomalies.append({
                    "service": service,
                    "metric": "error_count",
                    "value": float(row.get("error_count", 0)),
                    "threshold": float(row.get("baseline", 10)),
                    "severity": "high",
                    "detected_at": row.get("_time", datetime.utcnow().isoformat()),
                    "method": "error_spike",
                })
        except Exception as e:
            logger.warning(f"Error spike query failed: {e}")

        return anomalies

    def _classify_severity(self, anomalies: list, trigger: dict) -> str:
        """Classify P1-P4 based on anomaly count and trigger severity."""
        explicit = trigger.get("severity", "")
        if explicit in ("P1", "P2", "P3", "P4"):
            return explicit

        high_count = sum(1 for a in anomalies if a.get("severity") == "high")
        if high_count >= 3:
            return "P1"
        if high_count >= 1:
            return "P2"
        if len(anomalies) >= 2:
            return "P3"
        return "P4"

    def _fallback_anomaly(self, trigger: dict) -> dict:
        """Minimal anomaly record when detection fails."""
        return {
            "service": trigger.get("service", "unknown"),
            "metric": trigger.get("metric", "error_rate"),
            "value": trigger.get("value", 0.0),
            "threshold": trigger.get("threshold", 0.0),
            "severity": "high",
            "detected_at": datetime.utcnow().isoformat(),
            "method": "fallback",
        }

    async def _broadcast(self, incident_id: str, message: dict):
        if self.ws_broadcast:
            try:
                await self.ws_broadcast(incident_id, message)
            except Exception as e:
                logger.warning(f"WebSocket broadcast failed: {e}")
