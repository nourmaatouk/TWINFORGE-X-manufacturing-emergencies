"""
TWINFORGE — Structured JSON logging for all agent actions.
Implements the observability stack requirement.
"""
from __future__ import annotations
import json
import logging
import sys
from datetime import datetime
from collections import deque
from typing import Optional
from twinforge.core.schemas import AgentAction


# ═══════════════════════════════════════════════════════════
# ACTION LOG STORE (in-memory ring buffer)
# ═══════════════════════════════════════════════════════════

class ActionLogStore:
    """
    In-memory store for agent action logs.
    Keeps last N entries for dashboard display.
    """
    
    def __init__(self, max_entries: int = 500):
        self._logs: deque[dict] = deque(maxlen=max_entries)
    
    def add(self, action: AgentAction):
        self._logs.append(action.model_dump(mode="json"))
    
    def get_recent(self, n: int = 50) -> list[dict]:
        items = list(self._logs)
        return items[-n:]
    
    def get_all(self) -> list[dict]:
        return list(self._logs)
    
    def clear(self):
        self._logs.clear()


# Singleton
_action_store: Optional[ActionLogStore] = None

def get_action_store() -> ActionLogStore:
    global _action_store
    if _action_store is None:
        _action_store = ActionLogStore()
    return _action_store


# ═══════════════════════════════════════════════════════════
# STRUCTURED JSON FORMATTER
# ═══════════════════════════════════════════════════════════

class StructuredJSONFormatter(logging.Formatter):
    """Format log records as structured JSON for observability."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "agent_id"):
            log_entry["agent_id"] = record.agent_id
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = str(record.exc_info[1])
        return json.dumps(log_entry)


# ═══════════════════════════════════════════════════════════
# LOGGER SETUP
# ═══════════════════════════════════════════════════════════

def setup_logging(level: str = "INFO"):
    """Configure structured logging for all TWINFORGE modules."""
    root_logger = logging.getLogger("twinforge")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Console handler with structured format
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(StructuredJSONFormatter())
    root_logger.addHandler(console)
    
    return root_logger


def log_agent_action(
    agent_id: str,
    action: str,
    tool_used: str = "none",
    input_data: str = "",
    output_data: str = "",
    duration_ms: float = 0.0,
    success: bool = True,
    reasoning_trace: str = "",
    error: Optional[str] = None,
) -> AgentAction:
    """Log an agent action to both the logger and the action store."""
    from twinforge.core.security import compute_hash
    
    entry = AgentAction(
        agent_id=agent_id,
        action=action,
        tool_used=tool_used,
        input_hash=compute_hash(input_data) if input_data else "",
        output_hash=compute_hash(output_data) if output_data else "",
        duration_ms=duration_ms,
        success=success,
        reasoning_trace=reasoning_trace,
        error=error,
    )
    
    # Store in ring buffer
    get_action_store().add(entry)
    
    # Also log to standard logger
    logger = logging.getLogger(f"twinforge.agent.{agent_id}")
    msg = f"[{agent_id}] {action} | tool={tool_used} | {duration_ms:.0f}ms | {'✓' if success else '✗'}"
    if success:
        logger.info(msg)
    else:
        logger.error(msg)
    
    return entry
