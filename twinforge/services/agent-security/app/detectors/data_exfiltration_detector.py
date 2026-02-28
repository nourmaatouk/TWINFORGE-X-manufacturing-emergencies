"""
Data Exfiltration Detector - Monitors outbound data flows for suspicious patterns.

Detects attempts to leak sensitive data outside the TWINFORGE system:
1. Large payload sizes that could indicate bulk data extraction
2. Sensitive data patterns (API keys, credentials, PII) in outbound messages
3. Outbound data volume spikes per agent
4. External URL/endpoint references in payloads
5. Base64-encoded blobs that could hide exfiltrated data
"""

import re
import logging
from typing import Any
from collections import defaultdict
import time

logger = logging.getLogger(__name__)

# Patterns that indicate sensitive data in payloads
SENSITIVE_DATA_PATTERNS = [
    (r"(?:api[_-]?key|apikey)\s*[:=]\s*\S+", "API key"),
    (r"(?:password|passwd|pwd)\s*[:=]\s*\S+", "password"),
    (r"(?:secret|token)\s*[:=]\s*\S+", "secret/token"),
    (r"(?:aws_access_key_id|aws_secret_access_key)\s*[:=]\s*\S+", "AWS credential"),
    (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", "private key"),
    (r"(?:Bearer|Basic)\s+[A-Za-z0-9+/=]{20,}", "auth token"),
    (r"vault_token\s*[:=]\s*\S+", "Vault token"),
    (r"CLAUDE_API_KEY\s*[:=]\s*\S+", "Claude API key"),
    (r"MESSAGE_SIGNING_KEY\s*[:=]\s*\S+", "signing key"),
]

# Patterns that indicate external endpoint references
EXTERNAL_ENDPOINT_PATTERNS = [
    r"https?://(?!localhost|127\.0\.0\.1|10\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)\S+",
    r"ftp://\S+",
    r"s3://\S+",
    r"gs://\S+",
]

# Thresholds
MAX_PAYLOAD_SIZE = 100_000          # characters - suspiciously large payload
MAX_OUTBOUND_BYTES_PER_MINUTE = 500_000  # bytes per agent per minute
BASE64_MIN_LENGTH = 200             # minimum base64 block to flag


class DataExfiltrationDetector:
    """
    Detects data exfiltration attempts by monitoring outbound data flows.
    """

    def __init__(self):
        self._sensitive_patterns = [
            (re.compile(p, re.IGNORECASE), label)
            for p, label in SENSITIVE_DATA_PATTERNS
        ]
        self._external_patterns = [
            re.compile(p, re.IGNORECASE) for p in EXTERNAL_ENDPOINT_PATTERNS
        ]
        self._base64_pattern = re.compile(
            r"[A-Za-z0-9+/]{" + str(BASE64_MIN_LENGTH) + r",}={0,2}"
        )
        # Track outbound data volume: agent -> [(timestamp, size)]
        self._outbound_volume: dict[str, list[tuple[float, int]]] = defaultdict(list)

    def detect(self, payload: dict[str, Any], source_agent: str) -> dict:
        """
        Analyze payload for data exfiltration indicators.

        Args:
            payload: The message payload dict.
            source_agent: The agent sending the data.

        Returns:
            dict with threat_detected and details.
        """
        issues = []
        text = self._extract_text(payload)
        payload_size = len(text)

        # --- Check 1: Sensitive data patterns ---
        found_sensitive = self._scan_sensitive_data(text)
        if found_sensitive:
            issues.append({
                "check": "sensitive_data_leak",
                "severity": "CRITICAL",
                "detail": (
                    f"Sensitive data found in payload from '{source_agent}': "
                    f"{', '.join(found_sensitive)}"
                ),
            })

        # --- Check 2: Oversized payload ---
        if payload_size > MAX_PAYLOAD_SIZE:
            issues.append({
                "check": "oversized_payload",
                "severity": "HIGH",
                "detail": (
                    f"Abnormally large payload ({payload_size} chars) from "
                    f"'{source_agent}' - possible bulk data extraction"
                ),
            })

        # --- Check 3: External endpoint references ---
        external_urls = self._scan_external_endpoints(text)
        if external_urls:
            issues.append({
                "check": "external_endpoint",
                "severity": "HIGH",
                "detail": (
                    f"External endpoint references in payload from '{source_agent}': "
                    f"{external_urls[:3]}"  # limit to first 3
                ),
            })

        # --- Check 4: Suspicious base64 blobs ---
        b64_matches = self._base64_pattern.findall(text)
        if b64_matches:
            total_b64 = sum(len(m) for m in b64_matches)
            if total_b64 > 500:  # significant amount of base64
                issues.append({
                    "check": "base64_blob",
                    "severity": "MEDIUM",
                    "detail": (
                        f"Large base64-encoded data ({total_b64} chars in "
                        f"{len(b64_matches)} block(s)) from '{source_agent}'"
                    ),
                })

        # --- Check 5: Outbound data volume spike ---
        now = time.time()
        self._outbound_volume[source_agent].append((now, payload_size))
        cutoff = now - 60
        self._outbound_volume[source_agent] = [
            (ts, sz) for ts, sz in self._outbound_volume[source_agent] if ts > cutoff
        ]
        total_volume = sum(sz for _, sz in self._outbound_volume[source_agent])
        if total_volume > MAX_OUTBOUND_BYTES_PER_MINUTE:
            issues.append({
                "check": "volume_spike",
                "severity": "MEDIUM",
                "detail": (
                    f"Outbound data volume spike from '{source_agent}': "
                    f"{total_volume} chars/min (limit: {MAX_OUTBOUND_BYTES_PER_MINUTE})"
                ),
            })

        if not issues:
            return {"threat_detected": False}

        severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        worst = max(issues, key=lambda i: severity_rank.get(i["severity"], 0))

        confidence_map = {"CRITICAL": 0.95, "HIGH": 0.85, "MEDIUM": 0.7, "LOW": 0.5}
        confidence = min(1.0, confidence_map.get(worst["severity"], 0.5) + 0.04 * (len(issues) - 1))

        all_details = "; ".join(i["detail"] for i in issues)
        action = "BLOCK" if worst["severity"] in ("CRITICAL", "HIGH") else "ALERT"

        logger.warning(
            f"Data exfiltration detected from {source_agent}: "
            f"severity={worst['severity']}, checks={[i['check'] for i in issues]}"
        )

        return {
            "threat_detected": True,
            "threat_type": "DATA_EXFILTRATION",
            "severity": worst["severity"],
            "confidence": round(confidence, 2),
            "details": all_details,
            "recommended_action": action,
        }

    def _extract_text(self, obj: Any) -> str:
        """Recursively extract all string values from nested structures."""
        parts = []
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                parts.append(self._extract_text(v))
        elif isinstance(obj, list):
            for item in obj:
                parts.append(self._extract_text(item))
        return " ".join(parts)

    def _scan_sensitive_data(self, text: str) -> list[str]:
        """Scan for sensitive data patterns. Returns list of matched labels."""
        if not text:
            return []
        found = []
        for pattern, label in self._sensitive_patterns:
            if pattern.search(text):
                found.append(label)
        return found

    def _scan_external_endpoints(self, text: str) -> list[str]:
        """Find external URL references."""
        if not text:
            return []
        urls = []
        for pattern in self._external_patterns:
            urls.extend(pattern.findall(text))
        return urls
