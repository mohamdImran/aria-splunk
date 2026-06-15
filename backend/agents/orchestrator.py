"""
ARIA Agent Orchestrator — LangGraph Supervisor Pattern (async-native).

Architecture decision:
  FastAPI runs on an asyncio event loop.  All agent nodes are async coroutines.
  We therefore run the pipeline as a native async sequential chain and use
  LangGraph only when it can be invoked asynchronously (ainvoke).  The old
  pattern of wrapping async coroutines with run_until_complete() inside a
  ThreadPoolExecutor is fundamentally broken in an asyncio application — it
  raises "no current event loop in thread" and is removed entirely.

Flow:
  Sentinel → Forensic → Propagation → Remediation → [Approval?] → Commander
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from agents.shared_state import ARIAState, empty_state
from agents.sentinel_agent    import SentinelAgent
from agents.forensic_agent    import ForensicAgent
from agents.propagation_agent import PropagationAgent
from agents.remediation_agent import RemediationAgent
from splunk.mcp_client        import SplunkMCPClient

logger = logging.getLogger(__name__)

# ── Optional LangGraph import (async path only) ────────────────────────────
try:
    from langgraph.graph import StateGraph, END          # type: ignore
    _LANGGRAPH = True
except ImportError:
    _LANGGRAPH = False
    logger.info("LangGraph not installed — using native async pipeline")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ARIAOrchestrator:
    """
    Async-native multi-agent orchestrator.

    The pipeline is always executed as a sequence of awaitable coroutines.
    LangGraph's `ainvoke` is used when available; otherwise the same logic
    runs directly via ``_run_pipeline``.
    """

    def __init__(
        self,
        mcp_client:   SplunkMCPClient,
        ws_broadcast: Optional[Callable] = None,
        redis_client  = None,
    ) -> None:
        self.mcp          = mcp_client
        self.ws_broadcast = ws_broadcast
        self.redis        = redis_client

        # Specialised agents share the same MCP client and broadcast channel
        self.sentinel    = SentinelAgent(mcp_client, ws_broadcast)
        self.forensic    = ForensicAgent(mcp_client, ws_broadcast)
        self.propagation = PropagationAgent(mcp_client, ws_broadcast)
        self.remediation = RemediationAgent(mcp_client, ws_broadcast)

        # Per-incident human-approval synchronisation primitives
        self._approval_events:    dict[str, asyncio.Event] = {}
        self._approval_decisions: dict[str, dict]          = {}

        # Build LangGraph compiled graph once (async nodes only)
        self._lg_graph = self._build_lg_graph() if _LANGGRAPH else None

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    async def run_incident(
        self,
        incident_id:   str,
        trigger_event: dict,
        severity:      str = "P2",
    ) -> ARIAState:
        """
        Run the full ARIA pipeline for a new incident.

        Returns the final ARIAState after all agents have completed.
        State is persisted to Redis (if available) after each step.
        """
        state = empty_state(incident_id, trigger_event, severity)

        await self._broadcast(incident_id, {
            "type":        "incident_started",
            "incident_id": incident_id,
            "severity":    severity,
            "trigger":     trigger_event,
            "ts":          _utcnow(),
        })

        # Prefer LangGraph async path; fall back to native pipeline
        if self._lg_graph is not None:
            try:
                state = await self._run_lg(state)
            except Exception as exc:
                logger.warning(
                    "LangGraph ainvoke failed (%s) — running native pipeline", exc
                )
                state = await self._run_pipeline(state)
        else:
            state = await self._run_pipeline(state)

        state["completed_at"] = _utcnow()
        await self._persist(incident_id, state)
        return state

    async def submit_approval(
        self,
        incident_id: str,
        approved:    bool,
        notes:       str = "",
    ) -> None:
        """
        Called by the WebSocket handler when the operator submits a decision.
        Unblocks ``_approval_gate`` for the given incident.
        """
        self._approval_decisions[incident_id] = {
            "approved":    approved,
            "notes":       notes,
            "decided_at":  _utcnow(),
        }
        event = self._approval_events.get(incident_id)
        if event:
            event.set()
        else:
            logger.warning(
                "submit_approval: no pending gate for incident %s", incident_id
            )

    # ──────────────────────────────────────────────────────────────────────────
    # LangGraph path (async nodes)
    # ──────────────────────────────────────────────────────────────────────────

    def _build_lg_graph(self):
        """
        Compile a LangGraph StateGraph whose nodes are all async coroutines.
        Each node is a thin lambda that awaits the corresponding agent method.
        """
        wf = StateGraph(ARIAState)

        # Async node wrappers — LangGraph calls these and awaits the result
        wf.add_node("sentinel",    self.sentinel.run)
        wf.add_node("forensic",    self.forensic.run)
        wf.add_node("propagation", self.propagation.run)
        wf.add_node("remediation", self.remediation.run)
        wf.add_node("approval",    self._approval_gate)
        wf.add_node("commander",   self._commander)

        wf.set_entry_point("sentinel")
        wf.add_edge("sentinel",    "forensic")
        wf.add_edge("forensic",    "propagation")
        wf.add_edge("propagation", "remediation")

        wf.add_conditional_edges(
            "remediation",
            lambda s: "approval" if s.get("requires_approval") else "commander",
            {"approval": "approval", "commander": "commander"},
        )

        wf.add_edge("approval", "commander")
        wf.add_edge("commander", END)

        return wf.compile()

    async def _run_lg(self, state: ARIAState) -> ARIAState:
        """Invoke the compiled LangGraph graph asynchronously."""
        result = await self._lg_graph.ainvoke(state)
        return result  # type: ignore[return-value]

    # ──────────────────────────────────────────────────────────────────────────
    # Native async pipeline (used when LangGraph unavailable or fails)
    # ──────────────────────────────────────────────────────────────────────────

    async def _run_pipeline(self, state: ARIAState) -> ARIAState:
        """
        Sequential async execution — functionally identical to the LangGraph
        graph but implemented as plain await calls, which works perfectly
        inside FastAPI's asyncio event loop.
        """
        iid = state["incident_id"]

        steps: list[tuple[str, Callable]] = [
            ("sentinel",    self.sentinel.run),
            ("forensic",    self.forensic.run),
            ("propagation", self.propagation.run),
            ("remediation", self.remediation.run),
        ]

        for label, coro_fn in steps:
            logger.debug("Pipeline step: %s", label)
            try:
                updates = await coro_fn(state)
                state   = self._merge(state, updates)
            except Exception as exc:
                logger.exception("Agent %s raised an unhandled exception: %s", label, exc)
                state = self._merge(state, {"error": str(exc)})
            await self._persist(iid, state)

        # Human approval gate (only when required)
        if state.get("requires_approval"):
            state = await self._approval_gate(state)
            await self._persist(iid, state)

        # Commander synthesis
        updates = await self._commander(state)
        state   = self._merge(state, updates)
        await self._persist(iid, state)

        return state

    # ──────────────────────────────────────────────────────────────────────────
    # Approval gate
    # ──────────────────────────────────────────────────────────────────────────

    async def _approval_gate(self, state: ARIAState) -> ARIAState:
        """
        Suspend the pipeline until the operator approves or rejects via
        the WebSocket endpoint.

        Auto-approves low-risk runbooks after a configurable countdown.
        """
        from config import settings

        iid   = state["incident_id"]
        steps = state.get("runbook", {}).get("steps", [])

        all_low_risk = bool(steps) and all(
            s.get("risk") in ("Low",) for s in steps
        )

        if all_low_risk and settings.AUTO_APPROVE_LOW_RISK:
            timeout = settings.AUTO_APPROVE_TIMEOUT_SECONDS
            logger.info(
                "All runbook steps are Low risk — auto-approving in %ds", timeout
            )
            await self._broadcast(iid, {
                "type":    "auto_approve_countdown",
                "seconds": timeout,
                "reason":  "All steps are Low risk",
            })
            await asyncio.sleep(timeout)
            return self._merge(state, {
                "approved":          True,
                "approval_decision": "auto",
            })

        # Register a fresh asyncio.Event for this incident
        event = asyncio.Event()
        self._approval_events[iid] = event

        await self._broadcast(iid, {
            "type":    "approval_required",
            "runbook": state.get("runbook", {}),
        })

        try:
            await asyncio.wait_for(event.wait(), timeout=300.0)   # 5-minute window
        except asyncio.TimeoutError:
            logger.warning("Approval timed out for incident %s", iid)
            return self._merge(state, {
                "approved":          False,
                "approval_decision": "timeout",
                "approval_notes":    "Auto-rejected: operator did not respond within 5 minutes.",
            })
        finally:
            self._approval_events.pop(iid, None)

        decision = self._approval_decisions.pop(iid, {})
        approved  = bool(decision.get("approved", False))
        return self._merge(state, {
            "approved":          approved,
            "approval_decision": "approve" if approved else "reject",
            "approval_notes":    decision.get("notes", ""),
        })

    # ──────────────────────────────────────────────────────────────────────────
    # Commander synthesis
    # ──────────────────────────────────────────────────────────────────────────

    async def _commander(self, state: ARIAState) -> dict:
        """
        Synthesise the final Incident Brief from all agent outputs and
        broadcast it to the frontend.  Also creates a Splunk monitoring
        alert for post-incident surveillance.
        """
        iid        = state["incident_id"]
        root_cause = state.get("root_cause") or "unknown"
        confidence = state.get("confidence_score", 0.0)
        blast      = state.get("blast_radius", [])
        chain      = state.get("causal_chain", [])
        severity   = state.get("severity", "P2")
        approved   = state.get("approved", False)

        # Build human-readable causal chain string
        if chain:
            nodes = [chain[0]["cause"]] + [c["effect"] for c in chain]
            chain_str = " → ".join(nodes)
        else:
            chain_str = root_cause.replace("_", " ").title()

        critical = [b["service"] for b in blast if b.get("priority") == "critical"]
        at_risk  = len(blast)
        service  = state["trigger_event"].get("service", "unknown")

        brief = (
            f"## ARIA Incident Brief — {severity}\n\n"
            f"**Service:** `{service}`\n\n"
            f"### Root Cause\n\n"
            f"{root_cause.replace('_', ' ').title()} — **{confidence:.0%} confidence**\n\n"
            f"### Causal Chain\n\n"
            f"`{chain_str}`\n\n"
            f"### Blast Radius\n\n"
            f"**{at_risk}** services at risk"
            + (f"\n\n**Critical services:** {', '.join(f'`{s}`' for s in critical)}" if critical else "")
            + f"\n\n"
            f"### Remediation\n\n"
            + ("✅ Approved — executing runbook" if approved else "⏳ Pending operator approval")
            + f"\n\n"
            f"---\n\n"
            f"*Generated by ARIA at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*"
        )

        await self._broadcast(iid, {
            "type":     "agent_status",
            "agent_id": "commander",
            "status":   "done",
            "task":     "Incident brief synthesised",
            "finding":  f"Root cause: {root_cause} ({confidence:.0%}). {at_risk} services at risk.",
            "confidence": confidence,
        })

        await self._broadcast(iid, {
            "type":        "incident_brief",
            "brief":       brief,
            "incident_id": iid,
        })

        # Best-effort Splunk monitoring alert (failure is non-critical)
        try:
            await self.mcp.create_alert(
                name=f"ARIA_monitor_{iid}",
                search=(
                    f'index=main service="{service}" error_rate > 5 '
                    f'| stats avg(error_rate) as rate | where rate > 5'
                ),
                threshold=5.0,
            )
        except Exception as exc:
            logger.debug("Could not create post-incident alert: %s", exc)

        await self._broadcast(iid, {
            "type":        "incident_completed",
            "incident_id": iid,
            "brief":       brief,
            "ts":          _utcnow(),
        })

        return {
            "incident_brief": brief,
            "summary":        brief,
            "current_agent":  "commander",
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _merge(state: ARIAState, updates: dict) -> ARIAState:
        """
        Merge partial agent output into the current state.
        List-typed keys that are annotated as append-only are concatenated;
        all other keys are replaced.
        """
        _APPEND_KEYS = frozenset({
            "anomalies", "causal_chain", "blast_radius",
            "remediation_steps", "agent_messages",
        })
        merged = dict(state)
        for key, value in updates.items():
            if key in _APPEND_KEYS and isinstance(value, list):
                merged[key] = list(merged.get(key) or []) + value
            else:
                merged[key] = value
        return ARIAState(**merged)  # type: ignore[call-arg]

    async def _persist(self, incident_id: str, state: ARIAState) -> None:
        """Write state snapshot to Redis with a 1-hour TTL, and to in-memory cache."""
        # Always write to in-memory cache first (zero-cost, instant replay)
        from main import cache_incident_state
        try:
            cache_incident_state(incident_id, dict(state))
        except Exception:
            pass   # main not fully initialised during tests

        if self.redis is None:
            return
        try:
            await self.redis.setex(
                f"aria:incident:{incident_id}",
                3600,
                json.dumps(state, default=str),
            )
        except Exception as exc:
            logger.warning("Redis persist failed for %s: %s", incident_id, exc)

    async def _broadcast(self, incident_id: str, message: dict) -> None:
        """Send a WebSocket message to all clients watching this incident."""
        if self.ws_broadcast is None:
            return
        try:
            await self.ws_broadcast(incident_id, message)
        except Exception as exc:
            logger.debug("Broadcast error for %s: %s", incident_id, exc)
