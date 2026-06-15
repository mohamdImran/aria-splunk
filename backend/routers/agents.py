"""
Agents REST API router.
GET /api/agents                  — list all agent definitions
GET /api/agents/{agent_id}/status — get current agent status for an incident
"""
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(tags=["agents"])

AGENT_DEFINITIONS = {
    "sentinel": {
        "id": "sentinel",
        "name": "Sentinel",
        "role": "Anomaly Detection",
        "description": "Continuously monitors Splunk for anomalies across all services. "
                       "First agent to activate on alert. Classifies incident severity P1-P4.",
        "tools": ["splunk_search", "splunk_get_alerts", "splunk_get_metrics"],
        "icon": "",
    },
    "forensic": {
        "id": "forensic",
        "name": "Forensic",
        "role": "Causal Root Cause Analysis",
        "description": "Runs true causal inference (not correlation) using PC algorithm + DoWhy. "
                       "Identifies root cause with confidence score and generates counterfactuals.",
        "tools": ["splunk_search", "splunk_get_metrics", "splunk_run_model"],
        "icon": "",
    },
    "propagation": {
        "id": "propagation",
        "name": "Propagation",
        "role": "Blast Radius Prediction",
        "description": "BFS over causal graph to predict which services WILL fail next. "
                       "Provides 3-5 minute early warning with impact probability and ETA.",
        "tools": ["splunk_get_metrics", "splunk_search"],
        "icon": "",
    },
    "remediation": {
        "id": "remediation",
        "name": "Remediation",
        "role": "Auto-Remediation",
        "description": "Generates step-by-step runbook from root cause. "
                       "Executes approved steps via Splunk MCP. Supports human-in-the-loop approval.",
        "tools": ["splunk_execute_action", "splunk_create_alert", "splunk_update_dashboard"],
        "icon": "",
    },
}


@router.get("/agents", tags=["agents"])
async def list_agents():
    """List all ARIA agent definitions."""
    return list(AGENT_DEFINITIONS.values())


@router.get("/agents/{agent_id}", tags=["agents"])
async def get_agent(agent_id: str):
    """Get a specific agent definition."""
    agent = AGENT_DEFINITIONS.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent


@router.get("/agents/{agent_id}/status", tags=["agents"])
async def get_agent_status(
    agent_id: str,
    incident_id: Optional[str] = Query(None),
):
    """
    Get current status of an agent for a given incident.
    Returns live status, current task, finding, and confidence.
    """
    if agent_id not in AGENT_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # In a real deployment, fetch from Redis state
    from main import get_incident_state
    state = None
    if incident_id:
        state = await get_incident_state(incident_id)

    if not state:
        return {
            "agent_id": agent_id,
            "status": "idle",
            "current_task": "",
            "finding": "",
            "confidence": 0.0,
        }

    # Extract agent-specific data from state
    messages = state.get("agent_messages", [])
    agent_msgs = [m for m in messages if m.get("from_agent") == agent_id]

    return {
        "agent_id": agent_id,
        "incident_id": incident_id,
        "status": "done" if state.get("completed_at") else "working",
        "current_task": f"Processing incident {incident_id}",
        "finding": agent_msgs[-1]["content"] if agent_msgs else "",
        "confidence": state.get("confidence_score", 0.0),
    }
