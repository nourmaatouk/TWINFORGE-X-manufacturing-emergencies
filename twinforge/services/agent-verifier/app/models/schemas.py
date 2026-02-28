"""
Pydantic schemas for the Verifier Agent.
"""

from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime


class AgentRequest(BaseModel):
    session_id: str
    tenant_id: str = ""
    source_agent: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    message_signature: str = ""


class AgentResponse(BaseModel):
    session_id: str
    agent_id: str
    status: str = "success"
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    message_signature: str = ""


class VerificationResult(BaseModel):
    is_valid: bool
    verification_type: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
