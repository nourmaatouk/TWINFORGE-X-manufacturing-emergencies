"""
TWINFORGE — Security module.
Prompt injection prevention, PII detection, input sanitization.
"""
from __future__ import annotations
import re
import hashlib
import logging
from datetime import datetime
from twinforge.core.schemas import AgentAction

logger = logging.getLogger("twinforge.security")


# ═══════════════════════════════════════════════════════════
# PROMPT INJECTION PATTERNS
# ═══════════════════════════════════════════════════════════

INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions?|prompts?)",
    r"you\s+are\s+now\s+",
    r"system\s*:\s*",
    r"<\s*system\s*>",
    r"override\s+(your|the|all)\s+(rules?|instructions?|settings?)",
    r"pretend\s+(you|to)\s+(are|be)\s+",
    r"act\s+as\s+(if|a)\s+",
    r"reveal\s+(your|the|my)?\s*(system\s+)?(prompt|instructions?)",
    r"(show|print|display|output)\s+(me\s+)?(your|the|my)?\s*(system\s+)?prompt",
    r"admin\s+(access|mode|override|privileges?)",
    r"jailbreak",
    r"DAN\s+mode",
    r"bypass\s+(safety|filter|restriction)",
    r"\[INST\]",
    r"<<SYS>>",
    r"<script[\s>]",
    r"onerror\s*=",
]

COMPILED_INJECTION = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

# ═══════════════════════════════════════════════════════════
# PII DETECTION PATTERNS
# ═══════════════════════════════════════════════════════════

PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
}

# ═══════════════════════════════════════════════════════════
# SECURITY FUNCTIONS
# ═══════════════════════════════════════════════════════════

def check_prompt_injection(text: str) -> tuple[bool, str]:
    """
    Check input for prompt injection attempts.
    Returns (is_safe, reason).
    """
    for pattern in COMPILED_INJECTION:
        match = pattern.search(text)
        if match:
            reason = f"Prompt injection detected: '{match.group()}'"
            log_security_event("PROMPT_INJECTION", text, reason)
            return False, reason
    return True, "OK"


def detect_pii(text: str) -> list[dict[str, str]]:
    """Detect potential PII in text. Returns list of detections."""
    detections = []
    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            detections.append({
                "type": pii_type,
                "message": f"Potential {pii_type} detected in input"
            })
    return detections


def sanitize_input(text: str, max_length: int = 2048) -> str:
    """Sanitize user input: trim, strip dangerous chars, enforce length."""
    # Strip leading/trailing whitespace
    text = text.strip()
    # Enforce max length
    if len(text) > max_length:
        text = text[:max_length]
    # Remove null bytes
    text = text.replace("\x00", "")
    return text


def compute_hash(data: str) -> str:
    """Compute SHA-256 hash for audit logging."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def log_security_event(event_type: str, input_data: str, reason: str):
    """Log a security event."""
    event = {
        "event_type": f"SECURITY_EVENT:{event_type}",
        "input_hash": compute_hash(input_data),
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat(),
    }
    logger.warning(f"🔒 SECURITY EVENT: {event}")
