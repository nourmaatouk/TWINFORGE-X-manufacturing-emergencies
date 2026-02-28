"""
TWINFORGE Common Schemas
Shared Pydantic models used across all agents for request/response and event structures.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Enums ───────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    """Types of security events."""
    MESSAGE = "MESSAGE"
    TOOL_CALL = "TOOL_CALL"
    AUTH_ATTEMPT = "AUTH_ATTEMPT"
    DATA_ACCESS = "DATA_ACCESS"


class ThreatType(str, Enum):
    """Types of security threats."""
    PROMPT_INJECTION = "PROMPT_INJECTION"
    RAG_POISONING = "RAG_POISONING"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    DATA_EXFILTRATION = "DATA_EXFILTRATION"
    AGENT_SPOOFING = "AGENT_SPOOFING"
    ANOMALY = "ANOMALY"


class Severity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class RecommendedAction(str, Enum):
    """Recommended response actions."""
    BLOCK = "BLOCK"
    ALERT = "ALERT"
    LOG = "LOG"
    INVESTIGATE = "INVESTIGATE"


class AgentStatus(str, Enum):
    """Agent response statuses."""
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"


# ─── Request / Response ─────────────────────────────────────────────────────

class AgentRequest(BaseModel):
    """Standard agent request envelope."""
    session_id: str = Field(..., description="Unique session identifier")
    tenant_id: str = Field(default="default", description="Tenant identifier")
    source_agent: str = Field(..., description="ID of the requesting agent")
    payload: dict[str, Any] = Field(default_factory=dict, description="Request payload")
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    message_signature: str = Field(default="", description="HMAC-SHA256 signature")


class AgentResponse(BaseModel):
    """Standard agent response envelope."""
    session_id: str = Field(..., description="Session identifier")
    agent_id: str = Field(..., description="Responding agent ID")
    status: AgentStatus = Field(default=AgentStatus.SUCCESS, description="Response status")
    payload: dict[str, Any] = Field(default_factory=dict, description="Response payload")
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    message_signature: str = Field(default="", description="HMAC-SHA256 signature")


# ─── Security Events ────────────────────────────────────────────────────────

class SecurityEvent(BaseModel):
    """Security event from Agent 5."""
    event_type: EventType
    source_agent: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    message_signature: str = ""
    session_id: str = ""
    tenant_id: str = "default"


class ThreatReport(BaseModel):
    """Threat detection report from Agent 5."""
    threat_detected: bool = False
    threat_type: Optional[ThreatType] = None
    severity: Severity = Severity.LOW
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    details: str = ""
    recommended_action: RecommendedAction = RecommendedAction.LOG
    affected_agents: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
