"""
Alert Manager - Multi-channel alerting for security threats.

Sends alerts to:
1. Slack webhook (for team visibility)
2. PagerDuty webhook (for on-call escalation on CRITICAL)
3. Structured logs (always, as fallback)

Rate-limits alerts to avoid flooding notification channels.
"""

import logging
from typing import Any
from datetime import datetime, timezone
import time

import httpx

logger = logging.getLogger(__name__)

# Minimum seconds between alerts of the same type to avoid flooding
ALERT_COOLDOWN_SECONDS = 60


class AlertManager:
    """
    Sends security alerts to Slack and PagerDuty webhooks.
    Includes rate limiting to prevent notification fatigue.
    """

    def __init__(self, pagerduty_webhook: str = "", slack_webhook: str = ""):
        self.pagerduty_webhook = pagerduty_webhook
        self.slack_webhook = slack_webhook
        # Track last alert time per threat_type to rate-limit
        self._last_alert: dict[str, float] = {}
        self._http_client = httpx.AsyncClient(timeout=10.0)

    async def send_alert(self, threat: dict[str, Any]):
        """
        Send an alert for a detected threat.

        Args:
            threat: The threat detection result dict containing:
                - threat_type, severity, confidence, details, recommended_action
        """
        threat_type = threat.get("threat_type", "UNKNOWN")
        severity = threat.get("severity", "UNKNOWN")

        # Rate limit: don't send the same threat type more than once per cooldown
        now = time.time()
        last = self._last_alert.get(threat_type, 0)
        if now - last < ALERT_COOLDOWN_SECONDS:
            logger.debug(
                f"Alert suppressed for {threat_type} (cooldown: "
                f"{ALERT_COOLDOWN_SECONDS - (now - last):.0f}s remaining)"
            )
            return

        self._last_alert[threat_type] = now

        # Send to Slack
        if self.slack_webhook:
            await self._send_slack(threat)

        # Send to PagerDuty only for CRITICAL
        if self.pagerduty_webhook and severity == "CRITICAL":
            await self._send_pagerduty(threat)

        # Always log the alert
        logger.warning(
            f"ALERT SENT [{severity}] {threat_type}: {threat.get('details', '')[:200]}"
        )

    async def _send_slack(self, threat: dict[str, Any]):
        """Send a formatted Slack message via webhook."""
        severity = threat.get("severity", "UNKNOWN")
        emoji = {
            "CRITICAL": ":rotating_light:",
            "HIGH": ":warning:",
            "MEDIUM": ":large_orange_diamond:",
            "LOW": ":information_source:",
        }.get(severity, ":question:")

        message = {
            "text": (
                f"{emoji} *TWINFORGE Security Alert*\n"
                f"*Threat:* {threat.get('threat_type', 'UNKNOWN')}\n"
                f"*Severity:* {severity}\n"
                f"*Confidence:* {threat.get('confidence', 0):.0%}\n"
                f"*Details:* {threat.get('details', 'N/A')[:500]}\n"
                f"*Action:* {threat.get('recommended_action', 'LOG')}\n"
                f"*Time:* {datetime.now(timezone.utc).isoformat()}"
            )
        }

        try:
            resp = await self._http_client.post(self.slack_webhook, json=message)
            if resp.status_code != 200:
                logger.error(f"Slack webhook returned {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    async def _send_pagerduty(self, threat: dict[str, Any]):
        """Send a PagerDuty event via Events API v2."""
        event = {
            "routing_key": self.pagerduty_webhook,
            "event_action": "trigger",
            "payload": {
                "summary": (
                    f"[{threat.get('severity', 'UNKNOWN')}] "
                    f"{threat.get('threat_type', 'UNKNOWN')}: "
                    f"{threat.get('details', '')[:200]}"
                ),
                "source": "twinforge-agent-security",
                "severity": threat.get("severity", "warning").lower(),
                "component": "agent-security",
                "custom_details": {
                    "threat_type": threat.get("threat_type"),
                    "confidence": threat.get("confidence"),
                    "details": threat.get("details"),
                    "recommended_action": threat.get("recommended_action"),
                },
            },
        }

        try:
            resp = await self._http_client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=event,
            )
            if resp.status_code not in (200, 202):
                logger.error(f"PagerDuty API returned {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Failed to send PagerDuty alert: {e}")
