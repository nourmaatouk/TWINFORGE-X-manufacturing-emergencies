"""
TWINFORGE Message Signer
HMAC-SHA256 sign/verify functions for inter-agent messages.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MessageSigner:
    """Signs and verifies messages using HMAC-SHA256."""

    def __init__(self, secret_key: str) -> None:
        self._key = secret_key.encode("utf-8")

    def sign(self, message: dict[str, Any]) -> str:
        """Create HMAC-SHA256 signature for a message dict."""
        canonical = json.dumps(message, sort_keys=True, default=str)
        return hmac.new(self._key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(self, message: dict[str, Any], signature: str) -> bool:
        """Verify HMAC-SHA256 signature against a message dict."""
        expected = self.sign(message)
        return hmac.compare_digest(expected, signature)


def sign_message(message: dict[str, Any], secret_key: str) -> str:
    """Convenience function to sign a message."""
    return MessageSigner(secret_key).sign(message)


def verify_message(message: dict[str, Any], signature: str, secret_key: str) -> bool:
    """Convenience function to verify a message signature."""
    return MessageSigner(secret_key).verify(message, signature)
