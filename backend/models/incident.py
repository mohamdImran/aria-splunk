"""
Pydantic schemas for Incidents.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class Severity(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class IncidentStatus(str, Enum):
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"


class TriggerEvent(BaseModel):
    alert_name: str
    service: str
    metric: str
    value: float
    threshold: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw_data: Optional[dict] = None


class IncidentCreate(BaseModel):
    trigger_event: TriggerEvent
    severity: Severity = Severity.P2


class Incident(BaseModel):
    id: str
    severity: Severity
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    affected_services: List[str] = []
    brief: str = ""
    trigger_event: TriggerEvent
    confidence_score: float = 0.0
    root_cause: Optional[str] = None


class IncidentUpdate(BaseModel):
    status: Optional[IncidentStatus] = None
    brief: Optional[str] = None
    affected_services: Optional[List[str]] = None
    confidence_score: Optional[float] = None
    root_cause: Optional[str] = None
