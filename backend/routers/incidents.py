"""
Incidents REST API router.
GET  /api/incidents          — list all incidents
POST /api/incidents          — trigger new incident (start ARIA pipeline)
GET  /api/incidents/{id}     — get incident by ID
PATCH /api/incidents/{id}    — update incident status
DELETE /api/incidents/{id}   — delete/archive incident
"""
import asyncio
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Optional

from models.incident import Incident, IncidentCreate, IncidentUpdate, IncidentStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["incidents"])

# In-memory store (replace with DB for production)
_incidents: dict[str, Incident] = {}


@router.get("/incidents", response_model=list[Incident])
async def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
):
    """List all tracked incidents with optional filters."""
    incidents = list(_incidents.values())
    if status:
        incidents = [i for i in incidents if i.status == status]
    if severity:
        incidents = [i for i in incidents if i.severity == severity]
    return sorted(incidents, key=lambda i: i.start_time, reverse=True)[:limit]


@router.post("/incidents", response_model=Incident, status_code=201)
async def create_incident(
    payload: IncidentCreate,
    background_tasks: BackgroundTasks,
):
    """
    Trigger a new incident and start the ARIA agent pipeline.
    Returns immediately; pipeline runs in background.
    """
    from main import get_orchestrator

    incident_id = f"inc-{uuid.uuid4().hex[:8]}"
    incident = Incident(
        id=incident_id,
        severity=payload.severity,
        trigger_event=payload.trigger_event,
        start_time=datetime.utcnow(),
    )
    _incidents[incident_id] = incident

    # Start ARIA pipeline in background
    orchestrator = get_orchestrator()
    if orchestrator:
        background_tasks.add_task(
            _run_pipeline,
            orchestrator,
            incident,
            payload,
        )

    logger.info(f"Incident created: {incident_id} (severity={payload.severity})")
    return incident


@router.get("/incidents/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str):
    """Get a specific incident by ID."""
    incident = _incidents.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.patch("/incidents/{incident_id}", response_model=Incident)
async def update_incident(incident_id: str, update: IncidentUpdate):
    """Update incident status, brief, or affected services."""
    incident = _incidents.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    update_data = update.model_dump(exclude_none=True)
    updated = incident.model_copy(update=update_data)
    if update.status == IncidentStatus.RESOLVED:
        updated = updated.model_copy(update={"end_time": datetime.utcnow()})
    _incidents[incident_id] = updated
    return updated


@router.delete("/incidents/{incident_id}", status_code=204)
async def delete_incident(incident_id: str):
    """Archive/delete an incident."""
    if incident_id not in _incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    del _incidents[incident_id]


@router.post("/incidents/demo", response_model=Incident, status_code=201)
async def trigger_demo_incident(background_tasks: BackgroundTasks):
    """
    Trigger a pre-configured demo incident (checkout service DB pool exhaustion).
    Used for hackathon demos.
    """
    from models.incident import TriggerEvent, Severity
    demo_payload = IncidentCreate(
        severity=Severity.P2,
        trigger_event=TriggerEvent(
            alert_name="high_error_rate_checkout",
            service="checkout-service",
            metric="error_rate",
            value=14.7,
            threshold=5.0,
        ),
    )
    return await create_incident(demo_payload, background_tasks)


async def _run_pipeline(orchestrator, incident: Incident, payload: IncidentCreate):
    """Background task: run ARIA pipeline and update incident record."""
    try:
        _incidents[incident.id] = incident.model_copy(
            update={"status": IncidentStatus.INVESTIGATING}
        )
        final_state = await orchestrator.run_incident(
            incident_id=incident.id,
            trigger_event=payload.trigger_event.model_dump(mode="json"),
            severity=payload.severity.value,
        )
        # Update incident with pipeline results
        _incidents[incident.id] = _incidents[incident.id].model_copy(update={
            "status": IncidentStatus.REMEDIATING
                      if final_state.get("approved") else IncidentStatus.IDENTIFIED,
            "brief": final_state.get("incident_brief", ""),
            "confidence_score": final_state.get("confidence_score", 0.0),
            "root_cause": final_state.get("root_cause"),
            "affected_services": final_state.get("affected_services", []),
        })
    except Exception as e:
        logger.exception(f"Pipeline error for {incident.id}: {e}")
        _incidents[incident.id] = _incidents[incident.id].model_copy(
            update={"status": IncidentStatus.IDENTIFIED, "brief": f"Pipeline error: {e}"}
        )


def get_all_incidents() -> dict:
    return _incidents
