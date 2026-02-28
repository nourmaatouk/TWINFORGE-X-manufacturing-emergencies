"""
Agent Spoofing Detector - Verifies message authenticity via HMAC-SHA256 signatures.

Uses the shared message_signer.verify_payload() to check that messages
actually come from the agent they claim to be from. Also validates that
the source_agent is a known/registered agent ID.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Known valid agent IDs in the TWINFORGE system
REGISTERED_AGENTS = {
    "agent_1": "agent-conversation",
    "agent_2": "agent-orchestrator",
    "agent_3": "agent-data-iot",
    "agent_4": "agent-verifier",
    "agent_5": "agent-security",
    "langgraph": "langgraph-orchestrator",
    "dataset-replay": "dataset-replay",
    "mcp-mock-server": "mcp-mock-server",
}


class AgentSpoofingDetector:
    """
    Detects agent spoofing by verifying HMAC-SHA256 message signatures
    and validating source agent identity.
    """

    def __init__(self, signing_key: str = ""):
        self.signing_key = signing_key

    def detect(self, payload: dict[str, Any], signature: str, source_agent: str) -> dict:
        """
        Verify message authenticity.

        Checks:
        1. Source agent is a registered/known agent.
        2. Message signature is present.
        3. HMAC-SHA256 signature matches the payload.

        Args:
            payload: The message payload to verify.
            signature: The HMAC-SHA256 signature claimed by the sender.
            source_agent: The agent ID claimed by the sender.

        Returns:
            dict with threat_detected and details.
        """
        issues = []

        # Check 1: Is the source agent registered?
        if source_agent and source_agent not in REGISTERED_AGENTS:
            issues.append(f"Unknown agent ID: '{source_agent}' is not registered")

        # Check 2: Is a signature present?
        if not signature:
            # No signature at all - could be a spoofed message or misconfigured agent
            if source_agent:
                issues.append(f"Message from '{source_agent}' has no HMAC signature")
            else:
                issues.append("Message has no source agent and no signature")

        # Check 3: Verify the HMAC signature if we have a signing key and signature
        elif self.signing_key and signature:
            import hmac
            import hashlib
            import json

            canonical = json.dumps(payload, sort_keys=True)
            expected = hmac.new(
                self.signing_key.encode(),
                canonical.encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(expected, signature):
                issues.append(
                    f"HMAC signature mismatch for message from '{source_agent}' - "
                    f"message may be tampered or spoofed"
                )

        if not issues:
            return {"threat_detected": False}

        # Determine severity based on type of issue
        has_signature_mismatch = any("mismatch" in i for i in issues)
        has_unknown_agent = any("Unknown agent" in i for i in issues)

        if has_signature_mismatch:
            severity = "CRITICAL"
            confidence = 0.95
        elif has_unknown_agent:
            severity = "HIGH"
            confidence = 0.9
        else:
            # Missing signature - could be misconfiguration
            severity = "MEDIUM"
            confidence = 0.7

        action = "BLOCK" if severity in ("CRITICAL", "HIGH") else "ALERT"

        logger.warning(
            f"Agent spoofing detected: source={source_agent}, "
            f"severity={severity}, issues={issues}"
        )

        return {
            "threat_detected": True,
            "threat_type": "AGENT_SPOOFING",
            "severity": severity,
            "confidence": confidence,
            "details": "; ".join(issues),
            "recommended_action": action,
        }
