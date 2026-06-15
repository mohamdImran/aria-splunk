"""
Pydantic schemas for Runbooks.
"""
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class StepStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class RunbookStep(BaseModel):
    step: int
    action: str
    description: str
    risk: RiskLevel
    expected_outcome: str
    estimated_duration_seconds: int = 30
    status: StepStatus = StepStatus.PENDING
    spl_command: Optional[str] = None
    rollback_action: Optional[str] = None


class Runbook(BaseModel):
    id: str
    incident_id: str
    title: str
    steps: List[RunbookStep]
    generated_by: str = "remediation_agent"
    requires_approval: bool = True
    approved: bool = False
    execution_log: List[dict] = []


class RunbookCreate(BaseModel):
    incident_id: str
    title: str
    steps: List[RunbookStep]
