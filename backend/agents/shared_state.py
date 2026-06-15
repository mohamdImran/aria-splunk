"""
Shared ARIAState TypedDict for LangGraph multi-agent orchestration.
All agents read/write this state; Redis persists it across WebSocket sessions.
"""
from typing import TypedDict, Annotated, List, Optional, Dict, Any
import operator


class ARIAState(TypedDict):
    # ── Incident context ──────────────────────────────────────────────────
    incident_id: str
    trigger_event: dict             # Raw alert payload from Splunk
    severity: str                   # P1 / P2 / P3 / P4

    # ── Agent outputs (append-only via operator.add) ──────────────────────
    anomalies:         Annotated[List[dict], operator.add]
    causal_chain:      Annotated[List[dict], operator.add]
    blast_radius:      Annotated[List[dict], operator.add]
    remediation_steps: Annotated[List[dict], operator.add]
    agent_messages:    Annotated[List[dict], operator.add]

    # ── Causal analysis outputs ───────────────────────────────────────────
    causal_graph:      Optional[dict]   # {nodes, edges}
    root_cause:        Optional[str]
    confidence_score:  float
    counterfactuals:   Optional[List[dict]]

    # ── Blast radius ──────────────────────────────────────────────────────
    affected_services: List[str]

    # ── Final outputs ─────────────────────────────────────────────────────
    incident_brief: str
    runbook:        dict
    summary:        str

    # ── Control flow ──────────────────────────────────────────────────────
    current_agent:    str
    requires_approval: bool
    approved:          bool
    approval_decision: Optional[str]   # "approve" | "reject" | "modify"
    approval_notes:    Optional[str]

    # ── Metadata ──────────────────────────────────────────────────────────
    started_at:    str
    completed_at:  Optional[str]
    error:         Optional[str]


def empty_state(incident_id: str, trigger_event: dict, severity: str = "P2") -> ARIAState:
    """Create a fresh ARIAState for a new incident."""
    from datetime import datetime
    return ARIAState(
        incident_id=incident_id,
        trigger_event=trigger_event,
        severity=severity,
        anomalies=[],
        causal_chain=[],
        blast_radius=[],
        remediation_steps=[],
        agent_messages=[],
        causal_graph=None,
        root_cause=None,
        confidence_score=0.0,
        counterfactuals=None,
        affected_services=[],
        incident_brief="",
        runbook={},
        summary="",
        current_agent="sentinel",
        requires_approval=True,
        approved=False,
        approval_decision=None,
        approval_notes=None,
        started_at=datetime.utcnow().isoformat(),
        completed_at=None,
        error=None,
    )
