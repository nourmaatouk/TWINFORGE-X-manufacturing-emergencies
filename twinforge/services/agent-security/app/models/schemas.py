"""Pydantic schemas for the Security Agent."""

from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime


class SecurityEventRequest(BaseModel):
    event_type: str = "MESSAGE"
    source_agent: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    message_signature: str = ""
    session_id: str = ""
    tenant_id: str = ""


class ThreatResponse(BaseModel):
    threat_detected: bool = False
    threat_type: str | None = None
    severity: str | None = None
    confidence: float = 0.0
    details: str = ""
    recommended_action: str = "LOG"
    affected_agents: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
