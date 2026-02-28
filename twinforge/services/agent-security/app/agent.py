"""
Security Agent - Real-time security monitoring and threat detection.
Monitors all agent-to-agent communications and detects threats.

Features:
- 5 detectors with hybrid regex + LLM (o3) deep scan
- 3 monitors wired into the detection pipeline
- Elevated monitoring system (quarantine = forced deep scan, NOT hard-block)
- Auto-expiring quarantine (10 min) so the system never stops
- Rethinking loop: o3 re-evaluates threats and learns from attack patterns
- Incident logging + alerting
"""

import logging
import json
import time
from datetime import datetime, timezone
from typing import Any
from collections import defaultdict

from app.models.schemas import SecurityEventRequest, ThreatResponse
from app.detectors.prompt_injection_detector import PromptInjectionDetector
from app.detectors.rag_poisoning_detector import RAGPoisoningDetector
from app.detectors.privilege_escalation_detector import PrivilegeEscalationDetector
from app.detectors.data_exfiltration_detector import DataExfiltrationDetector
from app.detectors.agent_spoofing_detector import AgentSpoofingDetector
from app.monitors.message_bus_monitor import MessageBusMonitor
from app.monitors.tool_usage_monitor import ToolUsageMonitor
from app.monitors.anomaly_monitor import AnomalyMonitor
from app.responses.alert_manager import AlertManager
from app.responses.incident_logger import IncidentLogger
from app.llm_client import llm_client
from app.config import settings

logger = logging.getLogger(__name__)

# Quarantine thresholds (elevated monitoring, NOT hard-block)
QUARANTINE_THRESHOLD = 3   # CRITICAL/HIGH threats before elevated monitoring
QUARANTINE_WINDOW = 300    # 5-minute window for counting strikes
QUARANTINE_EXPIRY = 600    # 10 minutes — quarantine auto-lifts after this

RETHINK_SYSTEM_PROMPT = """You are an expert security reasoning engine for a manufacturing digital twin platform (TWINFORGE).

You will receive:
1. The original message payload
2. All detector results (threats found by regex, HMAC, permissions, etc.)
3. Recent attack history for this agent

Your job is to RETHINK the detection results:
- Are any of the detected threats likely false positives? If so, downgrade them.
- Are there attack patterns across multiple recent events that individual detectors missed?
- Could this be part of a coordinated multi-step attack?
- What is the true severity considering the full context?

Also extract any NEW attack patterns you notice that should be remembered for future detection.

Respond in EXACTLY this format:
FINAL_VERDICT: SAFE | LOW | MEDIUM | HIGH | CRITICAL
CONFIDENCE: 0.0 to 1.0
REASONING: 1-2 sentence explanation of your reasoning
FALSE_POSITIVES: comma-separated list of detector names that were false positives, or NONE
NEW_PATTERN: a regex pattern or description of a new attack technique found, or NONE
RECOMMENDATION: BLOCK | ALERT | LOG | QUARANTINE"""


class SecurityAgent:
    """Agent 5: Security Guardian - monitors and protects the multi-agent system."""

    def __init__(self):
        # Detectors
        self.prompt_injection_detector = PromptInjectionDetector()
        self.rag_poisoning_detector = RAGPoisoningDetector()
        self.privilege_escalation_detector = PrivilegeEscalationDetector()
        self.data_exfiltration_detector = DataExfiltrationDetector()
        self.agent_spoofing_detector = AgentSpoofingDetector(settings.MESSAGE_SIGNING_KEY)

        # Monitors
        self.message_bus_monitor = MessageBusMonitor()
        self.tool_usage_monitor = ToolUsageMonitor()
        self.anomaly_monitor = AnomalyMonitor()

        # Responses
        self.alert_manager = AlertManager(
            pagerduty_webhook=settings.ALERT_WEBHOOK_URL,
            slack_webhook=settings.SLACK_WEBHOOK_URL,
        )
        self.incident_logger = IncidentLogger(db_url=settings.POSTGRES_URL)

        # Quarantine: agent_id -> list of (timestamp, severity)
        self._strike_history: dict[str, list[tuple[float, str]]] = defaultdict(list)
        # Quarantine = elevated monitoring (NOT hard-block)
        # Maps agent_id -> timestamp when quarantine started (for auto-expiry)
        self._quarantined_agents: dict[str, float] = {}

        # Learning memory: stores attack patterns learned by o3
        self._learned_patterns: list[dict[str, Any]] = []
        self._max_learned = 200

    async def initialize(self):
        logger.info(f"Initializing {settings.AGENT_NAME} agent with o3 rethinking loop...")
        await self.incident_logger.init_db()

    async def shutdown(self):
        logger.info(f"Shutting down {settings.AGENT_NAME} agent...")

    def is_quarantined(self, agent_id: str) -> bool:
        """Check if an agent is currently under elevated monitoring (quarantine).
        Auto-expires after QUARANTINE_EXPIRY seconds."""
        if agent_id not in self._quarantined_agents:
            return False
        # Auto-expiry check
        started = self._quarantined_agents[agent_id]
        if time.time() - started > QUARANTINE_EXPIRY:
            del self._quarantined_agents[agent_id]
            logger.info(f"Quarantine auto-expired for agent '{agent_id}'")
            return False
        return True

    def release_quarantine(self, agent_id: str) -> bool:
        """Manually release an agent from quarantine."""
        if agent_id in self._quarantined_agents:
            del self._quarantined_agents[agent_id]
            logger.info(f"Agent '{agent_id}' released from quarantine")
            return True
        return False

    def get_quarantined(self) -> list[str]:
        """Return list of quarantined agent IDs (prune expired ones)."""
        now = time.time()
        expired = [aid for aid, ts in self._quarantined_agents.items()
                   if now - ts > QUARANTINE_EXPIRY]
        for aid in expired:
            del self._quarantined_agents[aid]
            logger.info(f"Quarantine auto-expired for agent '{aid}'")
        return list(self._quarantined_agents.keys())

    def get_learned_patterns(self) -> list[dict[str, Any]]:
        """Return patterns learned from attacks by the o3 rethinking loop."""
        return list(self._learned_patterns)

    async def analyze(self, request: SecurityEventRequest) -> ThreatResponse:
        """Run full detection pipeline: detectors → monitors → rethink → respond."""
        now = datetime.now(timezone.utc)
        under_quarantine = self.is_quarantined(request.source_agent)

        if under_quarantine:
            logger.warning(
                f"ELEVATED MONITORING: Agent '{request.source_agent}' is quarantined — "
                f"forcing full deep scan on every message"
            )

        threats = []

        # ===== PHASE 1: DETECTORS =====

        # 1. Prompt Injection (regex → LLM fallback, forced LLM if quarantined)
        pi_result = self.prompt_injection_detector.detect(request.payload, request.source_agent)
        if pi_result["threat_detected"]:
            threats.append(pi_result)
        if not pi_result["threat_detected"] or under_quarantine:
            pi_deep = await self.prompt_injection_detector.detect_deep(
                request.payload, request.source_agent
            )
            if pi_deep["threat_detected"]:
                threats.append(pi_deep)

        # 2. RAG Poisoning (regex → LLM for document events, forced LLM if quarantined)
        rag_result = self.rag_poisoning_detector.detect(request.payload, request.source_agent)
        if rag_result["threat_detected"]:
            threats.append(rag_result)
        if not rag_result["threat_detected"] or under_quarantine:
            if under_quarantine or request.event_type in ("DOCUMENT_INGESTION", "KNOWLEDGE_UPDATE", "RAG_QUERY"):
                rag_deep = await self.rag_poisoning_detector.detect_deep(
                    request.payload, request.source_agent
                )
                if rag_deep["threat_detected"]:
                    threats.append(rag_deep)

        # 3. Privilege Escalation
        pe_result = self.privilege_escalation_detector.detect(request.payload, request.source_agent)
        if pe_result["threat_detected"]:
            threats.append(pe_result)

        # 4. Data Exfiltration
        de_result = self.data_exfiltration_detector.detect(request.payload, request.source_agent)
        if de_result["threat_detected"]:
            threats.append(de_result)

        # 5. Agent Spoofing
        spoof_result = self.agent_spoofing_detector.detect(
            request.payload, request.message_signature, request.source_agent
        )
        if spoof_result["threat_detected"]:
            threats.append(spoof_result)

        # ===== PHASE 2: MONITORS =====

        # Tool usage tracking
        self.tool_usage_monitor.record(request.source_agent, request.event_type, request.payload)

        # Tool usage anomaly check
        tool_anomaly = self.tool_usage_monitor.check_anomalies(request.source_agent)
        if tool_anomaly["anomaly_detected"]:
            for issue in tool_anomaly["issues"]:
                threats.append({
                    "threat_detected": True,
                    "threat_type": "ANOMALY",
                    "severity": issue.get("severity", "MEDIUM"),
                    "confidence": 0.75,
                    "details": issue.get("detail", "Tool usage anomaly"),
                    "recommended_action": "ALERT",
                })

        # Anomaly monitor (statistical z-score on request patterns)
        anomaly_data = {
            "agent_id": request.source_agent,
            "payload_size": len(json.dumps(request.payload, default=str)),
        }
        anomaly_result = self.anomaly_monitor.check(anomaly_data)
        if anomaly_result["anomaly_detected"]:
            for a in anomaly_result["anomalies"]:
                threats.append({
                    "threat_detected": True,
                    "threat_type": "ANOMALY",
                    "severity": "MEDIUM",
                    "confidence": min(0.9, 0.5 + a.get("z_score", 3.0) * 0.1),
                    "details": (
                        f"Statistical anomaly on {a['metric']}: value={a['value']}, "
                        f"mean={a['mean']}, z={a['z_score']}"
                    ),
                    "recommended_action": "ALERT",
                })

        # Message bus monitor (if message has bus metadata)
        if request.payload.get("channel") or request.payload.get("sender_agent"):
            bus_result = self.message_bus_monitor.monitor(request.payload)
            if bus_result.get("has_issues"):
                for issue in bus_result["issues"]:
                    threats.append({
                        "threat_detected": True,
                        "threat_type": "ANOMALY",
                        "severity": issue.get("severity", "MEDIUM"),
                        "confidence": 0.8,
                        "details": issue.get("detail", "Message bus anomaly"),
                        "recommended_action": "ALERT",
                    })

        # ===== PHASE 3: RETHINKING LOOP (o3) =====
        # Force rethink for quarantined agents even if no threats found yet
        if (threats or under_quarantine) and llm_client.is_configured:
            rethink_result = await self._rethink(request, threats)
            if rethink_result:
                threats = [rethink_result]

        # ===== PHASE 4: RESPOND =====

        if threats:
            highest = max(threats, key=lambda t: self._severity_rank(t.get("severity", "LOW")))

            # Log incident
            await self.incident_logger.log(highest, request)

            # Track strikes for quarantine
            self._record_strike(request.source_agent, highest.get("severity", "LOW"))

            # Check if agent should be put under elevated monitoring
            if self._should_quarantine(request.source_agent):
                self._quarantined_agents[request.source_agent] = time.time()
                highest["details"] = (
                    f"{highest.get('details', '')} | "
                    f"ELEVATED MONITORING: Agent '{request.source_agent}' exceeded threat threshold — "
                    f"all messages will be deep-scanned for {QUARANTINE_EXPIRY // 60} minutes"
                )
                highest["recommended_action"] = "ALERT"
                logger.critical(
                    f"Agent '{request.source_agent}' placed under elevated monitoring "
                    f"(auto-expires in {QUARANTINE_EXPIRY // 60} min)"
                )

            # Fire alert if critical/high
            if highest.get("severity") in ("CRITICAL", "HIGH"):
                await self.alert_manager.send_alert(highest)

            return ThreatResponse(
                threat_detected=True,
                threat_type=highest.get("threat_type", "ANOMALY"),
                severity=highest.get("severity", "MEDIUM"),
                confidence=highest.get("confidence", 0.5),
                details=highest.get("details", "Threat detected"),
                recommended_action=highest.get("recommended_action", "ALERT"),
                affected_agents=[request.source_agent],
                timestamp=now,
            )

        return ThreatResponse(threat_detected=False, timestamp=now)

    async def _rethink(self, request: SecurityEventRequest, threats: list[dict]) -> dict | None:
        """
        o3 rethinking loop: re-evaluate all detector outputs with full context.
        Returns a single consolidated threat dict, or None to keep original threats.
        """
        # Build context for o3
        threat_summary = json.dumps(threats, default=str, indent=2)
        payload_summary = json.dumps(request.payload, default=str)[:2000]

        # Get recent attack history for this agent
        recent = self.incident_logger.get_recent(20)
        agent_history = [
            i for i in recent if i.get("source_agent") == request.source_agent
        ]
        history_summary = json.dumps(agent_history[-5:], default=str, indent=2) if agent_history else "No recent history"

        # Get learned patterns
        learned_summary = ""
        if self._learned_patterns:
            learned_summary = f"\n\nPreviously learned attack patterns:\n{json.dumps(self._learned_patterns[-10:], default=str, indent=2)}"

        user_content = (
            f"Source agent: {request.source_agent}\n"
            f"Event type: {request.event_type}\n\n"
            f"Payload:\n{payload_summary}\n\n"
            f"Detector results:\n{threat_summary}\n\n"
            f"Recent attack history for this agent:\n{history_summary}"
            f"{learned_summary}"
        )

        result = await llm_client.analyze(
            system_prompt=RETHINK_SYSTEM_PROMPT,
            user_content=user_content,
            max_tokens=500,
        )

        if not result["success"]:
            logger.warning(f"Rethink loop failed: {result.get('error')}")
            return None

        return self._parse_rethink_response(result["content"], request.source_agent)

    def _parse_rethink_response(self, response: str, source_agent: str) -> dict | None:
        """Parse o3 rethinking response and extract learned patterns."""
        verdict, confidence, reasoning = "SAFE", 0.0, ""
        false_positives, new_pattern, recommendation = "NONE", "NONE", "ALERT"

        for line in response.strip().split("\n"):
            line = line.strip()
            if line.startswith("FINAL_VERDICT:"):
                verdict = line.split(":", 1)[1].strip().upper()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                except ValueError:
                    confidence = 0.5
            elif line.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line.startswith("FALSE_POSITIVES:"):
                false_positives = line.split(":", 1)[1].strip()
            elif line.startswith("NEW_PATTERN:"):
                new_pattern = line.split(":", 1)[1].strip()
            elif line.startswith("RECOMMENDATION:"):
                recommendation = line.split(":", 1)[1].strip().upper()

        # Learn new pattern if o3 found one
        if new_pattern and new_pattern.upper() != "NONE":
            self._learn_pattern(new_pattern, source_agent, verdict)

        if verdict == "SAFE":
            logger.info(
                f"Rethink: o3 determined SAFE for {source_agent} "
                f"(false positives: {false_positives})"
            )
            return None  # Override: no threat

        logger.info(
            f"Rethink: o3 verdict={verdict}, confidence={confidence}, "
            f"reasoning={reasoning}, learned_pattern={new_pattern}"
        )

        return {
            "threat_detected": True,
            "threat_type": "RETHINK_CONFIRMED",
            "severity": verdict if verdict in ("CRITICAL", "HIGH", "MEDIUM", "LOW") else "MEDIUM",
            "confidence": round(confidence, 2),
            "details": f"[o3 Rethink] {reasoning}",
            "recommended_action": recommendation if recommendation in ("BLOCK", "ALERT", "LOG", "QUARANTINE") else "ALERT",
            "detection_method": "rethink_loop",
            "false_positives": false_positives,
        }

    def _learn_pattern(self, pattern: str, source_agent: str, severity: str):
        """Store a new attack pattern discovered by o3."""
        entry = {
            "pattern": pattern,
            "discovered_from": source_agent,
            "severity": severity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._learned_patterns.append(entry)
        if len(self._learned_patterns) > self._max_learned:
            self._learned_patterns = self._learned_patterns[-self._max_learned:]
        logger.info(f"Learned new attack pattern: {pattern}")

    def _record_strike(self, agent_id: str, severity: str):
        """Record a threat strike for quarantine tracking."""
        if severity in ("CRITICAL", "HIGH"):
            now = time.time()
            self._strike_history[agent_id].append((now, severity))
            # Prune old strikes
            cutoff = now - QUARANTINE_WINDOW
            self._strike_history[agent_id] = [
                (ts, s) for ts, s in self._strike_history[agent_id] if ts > cutoff
            ]

    def _should_quarantine(self, agent_id: str) -> bool:
        """Check if an agent has exceeded the quarantine threshold."""
        if agent_id in self._quarantined_agents:
            return False  # Already quarantined
        strikes = self._strike_history.get(agent_id, [])
        return len(strikes) >= QUARANTINE_THRESHOLD

    def _severity_rank(self, severity: str) -> int:
        return {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(severity, 0)
