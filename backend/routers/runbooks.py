"""
Runbooks REST API router.
GET    /api/runbooks               — list all runbooks
POST   /api/runbooks               — create runbook manually
GET    /api/runbooks/{id}          — get specific runbook
PATCH  /api/runbooks/{id}          — update runbook (modify step)
POST   /api/runbooks/{id}/approve  — approve runbook
POST   /api/runbooks/{id}/reject   — reject runbook
POST   /api/runbooks/{id}/execute  — execute approved runbook
"""
import logging
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional

from models.runbook import Runbook, RunbookCreate, RunbookStep, StepStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["runbooks"])

# In-memory store (replace with DB for production)
_runbooks: dict[str, Runbook] = {}


@router.get("/runbooks", response_model=list[Runbook])
async def list_runbooks(incident_id: Optional[str] = None):
    """List all runbooks, optionally filtered by incident."""
    books = list(_runbooks.values())
    if incident_id:
        books = [b for b in books if b.incident_id == incident_id]
    return books


@router.post("/runbooks", response_model=Runbook, status_code=201)
async def create_runbook(payload: RunbookCreate):
    """Manually create a runbook (also auto-created by Remediation Agent)."""
    rb_id = f"rb-{uuid.uuid4().hex[:8]}"
    runbook = Runbook(
        id=rb_id,
        incident_id=payload.incident_id,
        title=payload.title,
        steps=payload.steps,
        generated_by="manual",
        requires_approval=True,
    )
    _runbooks[rb_id] = runbook
    return runbook


@router.get("/runbooks/{runbook_id}", response_model=Runbook)
async def get_runbook(runbook_id: str):
    rb = _runbooks.get(runbook_id)
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return rb


@router.patch("/runbooks/{runbook_id}/steps/{step_number}", response_model=Runbook)
async def update_step(runbook_id: str, step_number: int, step_update: dict):
    """Modify a specific runbook step (human modification before approval)."""
    rb = _runbooks.get(runbook_id)
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook not found")

    updated_steps = []
    for s in rb.steps:
        if s.step == step_number:
            # Allow updating action, description, and risk
            s_dict = s.model_dump()
            s_dict.update({k: v for k, v in step_update.items()
                           if k in ("action", "description", "risk")})
            updated_steps.append(RunbookStep(**s_dict))
        else:
            updated_steps.append(s)

    updated = rb.model_copy(update={"steps": updated_steps})
    _runbooks[runbook_id] = updated
    return updated


@router.post("/runbooks/{runbook_id}/approve", response_model=Runbook)
async def approve_runbook(runbook_id: str, background_tasks: BackgroundTasks):
    """Approve a runbook and trigger execution."""
    rb = _runbooks.get(runbook_id)
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook not found")

    updated = rb.model_copy(update={"approved": True})
    _runbooks[runbook_id] = updated

    # Notify orchestrator of approval
    from main import get_orchestrator
    orchestrator = get_orchestrator()
    if orchestrator:
        background_tasks.add_task(
            orchestrator.submit_approval,
            rb.incident_id,
            True,
            "Approved via REST API",
        )

    return updated


@router.post("/runbooks/{runbook_id}/reject")
async def reject_runbook(runbook_id: str, reason: str = ""):
    """Reject a runbook and feed back into Remediation Agent."""
    rb = _runbooks.get(runbook_id)
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook not found")

    from main import get_orchestrator
    orchestrator = get_orchestrator()
    if orchestrator:
        await orchestrator.submit_approval(rb.incident_id, False, reason)

    return {"status": "rejected", "runbook_id": runbook_id, "reason": reason}


@router.post("/runbooks/{runbook_id}/execute")
async def execute_runbook(runbook_id: str, background_tasks: BackgroundTasks):
    """Execute an approved runbook (steps in sequence)."""
    rb = _runbooks.get(runbook_id)
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook not found")
    if not rb.approved:
        raise HTTPException(status_code=400, detail="Runbook not approved")

    background_tasks.add_task(_execute_runbook_steps, rb)
    return {"status": "executing", "runbook_id": runbook_id}


async def _execute_runbook_steps(rb: Runbook):
    """Execute runbook steps sequentially, updating status per step."""
    from main import get_orchestrator, get_incident_state
    orchestrator = get_orchestrator()

    for i, step in enumerate(rb.steps):
        # Update step to running
        rb.steps[i] = step.model_copy(update={"status": StepStatus.RUNNING})
        _runbooks[rb.id] = rb

        try:
            if orchestrator:
                state = await get_incident_state(rb.incident_id) or {}
                result = await orchestrator.remediation.execute_step(
                    rb.incident_id,
                    step.model_dump(),
                    state,  # type: ignore
                )
                new_status = StepStatus.COMPLETED if result["status"] == "completed" else StepStatus.FAILED
            else:
                new_status = StepStatus.COMPLETED

            rb.steps[i] = step.model_copy(update={"status": new_status})
        except Exception as e:
            logger.exception(f"Step {step.step} failed: {e}")
            rb.steps[i] = step.model_copy(update={"status": StepStatus.FAILED})

        _runbooks[rb.id] = rb


def store_runbook(rb: Runbook):
    """Called by orchestrator to register auto-generated runbooks."""
    _runbooks[rb.id] = rb
