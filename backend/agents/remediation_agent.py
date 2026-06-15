"""
Remediation Agent — Auto-Remediation Runbook Generation.

Responsibilities:
- Generate step-by-step runbook based on root cause + blast radius
- Classify risk per step (Low / Medium / High / Critical)
- Determine if human approval is required
- Execute approved actions via Splunk MCP
- Report execution status back to ARIAState
"""
import logging
from datetime import datetime
from typing import Optional

from agents.shared_state import ARIAState
from splunk.mcp_client import SplunkMCPClient

logger = logging.getLogger(__name__)


class RemediationAgent:
    """
    Automated runbook generator and executor.
    Low-risk steps can auto-approve; high-risk steps require human approval.
    """

    NAME = "remediation"
    DISPLAY_NAME = "Remediation"

    # Root cause → remediation strategy mapping
    REMEDIATION_MAP = {
        "db_connection_pool": [
            {
                "action": "Increase DB connection pool limit",
                "description": "Scale max_connections from 100 → 300 in db.conf",
                "risk": "Medium",
                "expected_outcome": "Connection wait queue cleared within 60s",
                "estimated_duration_seconds": 45,
                "rollback_action": "Revert max_connections to 100",
            },
            {
                "action": "Kill long-running DB queries",
                "description": "Terminate queries running > 30s to free connections",
                "risk": "Medium",
                "expected_outcome": "Connection pool utilization drops below 70%",
                "estimated_duration_seconds": 30,
                "rollback_action": "No rollback needed (queries already timed out)",
            },
            {
                "action": "Restart DB connection pooler (PgBouncer)",
                "description": "Graceful restart of connection pooler service",
                "risk": "High",
                "expected_outcome": "Fresh connection pool, ~5s downtime",
                "estimated_duration_seconds": 15,
                "rollback_action": "Start backup pooler instance",
            },
            {
                "action": "Scale API gateway replicas",
                "description": "Add 2 API gateway pods to distribute DB load",
                "risk": "Low",
                "expected_outcome": "Per-pod DB connection count reduced by 50%",
                "estimated_duration_seconds": 90,
                "rollback_action": "Scale back to original replica count",
            },
        ],
        "high_error_rate": [
            {
                "action": "Enable circuit breaker on affected service",
                "description": "Activate circuit breaker pattern to prevent cascade",
                "risk": "Low",
                "expected_outcome": "Error rate contained; upstream services protected",
                "estimated_duration_seconds": 20,
                "rollback_action": "Disable circuit breaker",
            },
            {
                "action": "Rollback to previous deployment",
                "description": "Rollback to last known good deployment",
                "risk": "High",
                "expected_outcome": "Error rate returns to baseline within 2 minutes",
                "estimated_duration_seconds": 120,
                "rollback_action": "Re-deploy current version",
            },
        ],
        "cpu_spike": [
            {
                "action": "Auto-scale service to 3x replicas",
                "description": "Trigger HPA scale-up to handle load spike",
                "risk": "Low",
                "expected_outcome": "CPU per replica drops below 60%",
                "estimated_duration_seconds": 60,
                "rollback_action": "Scale back to minimum replicas",
            },
        ],
        "memory_leak": [
            {
                "action": "Rolling restart of affected pods",
                "description": "Graceful rolling restart to clear memory leak",
                "risk": "Medium",
                "expected_outcome": "Memory usage normalizes; brief latency spike expected",
                "estimated_duration_seconds": 180,
                "rollback_action": "Manual restart if rolling restart fails",
            },
        ],
        "default": [
            {
                "action": "Create Splunk alert for continued monitoring",
                "description": "Set up automated alert for early warning on recurrence",
                "risk": "Low",
                "expected_outcome": "Alert fires within 5 minutes of metric threshold breach",
                "estimated_duration_seconds": 30,
                "rollback_action": "Delete alert",
            },
            {
                "action": "Page on-call engineer",
                "description": "Create PagerDuty incident for human escalation",
                "risk": "Low",
                "expected_outcome": "Engineer assigned within SLA",
                "estimated_duration_seconds": 60,
                "rollback_action": "Resolve PD incident if auto-remediated",
            },
        ],
    }

    def __init__(self, mcp_client: SplunkMCPClient, ws_broadcast=None):
        self.mcp = mcp_client
        self.ws_broadcast = ws_broadcast

    async def run(self, state: ARIAState) -> dict:
        """LangGraph node function."""
        incident_id = state["incident_id"]
        root_cause = state.get("root_cause", "unknown")
        blast_radius = state.get("blast_radius", [])
        severity = state.get("severity", "P2")
        causal_chain = state.get("causal_chain", [])

        await self._broadcast(incident_id, {
            "type": "agent_status",
            "agent_id": self.NAME,
            "status": "working",
            "task": f"Generating remediation runbook for root cause: {root_cause}",
            "finding": "",
            "confidence": 0.0,
        })

        try:
            # Generate runbook based on root cause pattern
            steps = self._generate_steps(root_cause, blast_radius, severity)

            # Determine approval requirement
            has_high_risk = any(
                s["risk"] in ("High", "Critical") for s in steps
            )
            requires_approval = has_high_risk or severity in ("P1",)

            runbook = {
                "id": f"rb-{incident_id}",
                "incident_id": incident_id,
                "title": f"Remediation: {root_cause.replace('_', ' ').title()}",
                "steps": [
                    {**step, "step": i + 1, "status": "pending"}
                    for i, step in enumerate(steps)
                ],
                "generated_by": self.NAME,
                "requires_approval": requires_approval,
                "approved": False,
                "execution_log": [],
            }

            finding = (
                f"Generated {len(steps)}-step runbook. "
                f"{'Requires approval for high-risk steps.' if requires_approval else 'Low-risk steps can auto-approve.'}"
            )

            await self._broadcast(incident_id, {
                "type": "agent_status",
                "agent_id": self.NAME,
                "status": "done",
                "task": "Runbook generated",
                "finding": finding,
                "confidence": 0.87,
            })

            await self._broadcast(incident_id, {
                "type": "agent_message",
                "from": self.NAME,
                "to": "commander",
                "content": (
                    f"📋 {len(steps)}-step runbook ready. "
                    f"{'⚠️ Human approval required for steps 2-3.' if requires_approval else '✅ All steps low-risk, can auto-execute.'} "
                    f"Awaiting {'approval gate' if requires_approval else 'execution confirmation'}."
                ),
                "ts": datetime.utcnow().isoformat(),
            })

            if requires_approval:
                await self._broadcast(incident_id, {
                    "type": "approval_required",
                    "runbook": runbook,
                })

            return {
                "remediation_steps": steps,
                "runbook": runbook,
                "requires_approval": requires_approval,
                "current_agent": "commander",
            }

        except Exception as e:
            logger.exception(f"Remediation agent error: {e}")
            fallback = self._fallback_runbook(incident_id, root_cause)
            return {
                "remediation_steps": fallback["steps"],
                "runbook": fallback,
                "requires_approval": True,
                "current_agent": "commander",
                "error": str(e),
            }

    async def execute_step(
        self,
        incident_id: str,
        step: dict,
        state: ARIAState,
    ) -> dict:
        """
        Execute an approved runbook step via Splunk MCP.
        Called by commander after approval.
        """
        action = step.get("action", "")
        logger.info(f"Executing step: {action}")

        await self._broadcast(incident_id, {
            "type": "execution_update",
            "step": step["step"],
            "action": action,
            "status": "running",
        })

        try:
            result = await self.mcp.execute_action(
                action=action,
                parameters={
                    "incident_id": incident_id,
                    "root_cause": state.get("root_cause"),
                    "step_details": step,
                },
            )

            await self._broadcast(incident_id, {
                "type": "execution_update",
                "step": step["step"],
                "action": action,
                "status": "completed",
                "result": result,
            })

            return {"status": "completed", "result": result}

        except Exception as e:
            await self._broadcast(incident_id, {
                "type": "execution_update",
                "step": step["step"],
                "action": action,
                "status": "failed",
                "error": str(e),
            })
            return {"status": "failed", "error": str(e)}

    # ── Runbook generation ─────────────────────────────────────────────────

    def _generate_steps(
        self,
        root_cause: str,
        blast_radius: list,
        severity: str,
    ) -> list:
        """Select and prioritize runbook steps based on root cause pattern."""
        # Match root cause to known pattern
        pattern = "default"
        for key in self.REMEDIATION_MAP:
            if key in root_cause.lower():
                pattern = key
                break

        steps = list(self.REMEDIATION_MAP.get(pattern, self.REMEDIATION_MAP["default"]))

        # Add monitoring step for critical blast radius
        if len([b for b in blast_radius if b.get("priority") == "critical"]) >= 2:
            steps.insert(0, {
                "action": "Create Splunk ITSI episode for blast radius monitoring",
                "description": "Group all at-risk services under unified ITSI episode",
                "risk": "Low",
                "expected_outcome": "Unified view of all impacted services",
                "estimated_duration_seconds": 20,
                "rollback_action": "Close ITSI episode",
            })

        # P1 gets an immediate isolation step prepended
        if severity == "P1":
            steps.insert(0, {
                "action": "Enable emergency traffic throttling",
                "description": "Rate-limit inbound traffic to 10% to prevent cascade",
                "risk": "High",
                "expected_outcome": "Error cascade stops within 30s",
                "estimated_duration_seconds": 10,
                "rollback_action": "Restore full traffic",
            })

        return steps

    def _fallback_runbook(self, incident_id: str, root_cause: str) -> dict:
        steps = [
            {
                "step": 1,
                "action": "Investigate root cause in Splunk",
                "description": f"Review logs for {root_cause}",
                "risk": "Low",
                "expected_outcome": "Root cause confirmed",
                "estimated_duration_seconds": 60,
                "status": "pending",
                "rollback_action": None,
            },
            {
                "step": 2,
                "action": "Page on-call engineer",
                "description": "Manual escalation required",
                "risk": "Low",
                "expected_outcome": "Engineer investigating",
                "estimated_duration_seconds": 60,
                "status": "pending",
                "rollback_action": None,
            },
        ]
        return {
            "id": f"rb-{incident_id}",
            "incident_id": incident_id,
            "title": f"Emergency Runbook: {root_cause}",
            "steps": steps,
            "generated_by": self.NAME,
            "requires_approval": True,
            "approved": False,
            "execution_log": [],
        }

    async def _broadcast(self, incident_id: str, message: dict):
        if self.ws_broadcast:
            try:
                await self.ws_broadcast(incident_id, message)
            except Exception as e:
                logger.warning(f"WebSocket broadcast failed: {e}")
