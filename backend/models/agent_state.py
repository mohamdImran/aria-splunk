"""
Pydantic schemas for Agent state.
"""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    DONE = "done"
    ERROR = "error"


class AgentState(BaseModel):
    agent_id: str
    name: str
    status: AgentStatus = AgentStatus.IDLE
    current_task: str = ""
    finding: str = ""
    confidence: float = 0.0
    error: Optional[str] = None


class AgentMessage(BaseModel):
    from_agent: str
    to_agent: str
    content: str
    message_type: str = "info"   # info | finding | request | handoff
    timestamp: str
