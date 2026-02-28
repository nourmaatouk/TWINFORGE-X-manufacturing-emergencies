"""
TWINFORGE — Agent 1: Conversation Agent.
Single entry point for all user interactions.
Translates natural language → structured JSON intent.
Translates agent responses → human-readable output.
Uses Google Gemini API for intent classification.
"""
from __future__ import annotations
import json
import re
import time
import logging
import requests
from datetime import datetime
from typing import Any

from twinforge.core.schemas import (
    UserInput, IntentResult, Intent, TwinResult
)
from twinforge.core.security import check_prompt_injection, detect_pii, sanitize_input
from twinforge.core.config import get_settings
from twinforge.core.logging_config import log_agent_action

logger = logging.getLogger("twinforge.agent.conversation")

AGENT_ID = "agent_1_conversation"

ASSET_TYPE_ALIASES: dict[str, str] = {
    "cnc": "CNC",
    "lathe": "Lathe",
    "mill": "Mill",
    "drill": "Drill",
    "press": "Press",
    "robot": "Robot",
    "conveyor": "Conveyor",
    "pump": "Pump",
    "motor": "Motor",
    "compressor": "Compressor",
    "3d printer": "3DPrinter",
    "assembly station": "AssemblyStation",
}


# ═══════════════════════════════════════════════════════════
# INTENT CLASSIFICATION — Rule-based fallback
# ═══════════════════════════════════════════════════════════

INTENT_PATTERNS: dict[Intent, list[str]] = {
    Intent.CREATE_TWIN: [
        r"create\s+(a\s+)?(digital\s+)?twin",
        r"create\s+(?:a\s+)?(?:new\s+)?(?:[a-zA-Z0-9_\-\s]+)?twin",  # Allow "create a CNC machine twin"
        r"create\s+(a\s+)?(?:cnc|robot|conveyor|lathe|press|drill|mill|machine)",
        r"build\s+(a\s+)?(digital\s+)?twin",
        r"make\s+(a\s+)?(digital\s+)?twin",
        r"new\s+(digital\s+)?twin",
        r"add\s+(a\s+)?(new\s+)?(digital\s+)?twin",
        r"add\s+(a\s+)?(?:cnc|robot|conveyor|lathe|press|drill|mill|machine)",
        r"generate\s+(a\s+)?(?:digital\s+)?(?:twin|machine)",
        r"ajoute[rz]?\s+(un|une|des)?\s*(jumeau|machine|cnc|robot)",
        r"set\s*up\s+(a\s+)?(digital\s+)?twin",
        r"model\s+(a\s+)?machine",
        r"cr[eé]+er?\s+(un\s+)?jumeau",
    ],
    Intent.QUERY_TWIN: [
        r"show\s+(me\s+)?(the\s+)?twin",
        r"get\s+(the\s+)?twin",
        r"details?\s+(of|for|about)\s+",
        r"info(rmation)?\s+(on|about|for)\s+",
        r"what\s+(is|are)\s+(the\s+)?twin",
        r"status\s+(of|for)",
    ],
    Intent.GET_KPI: [
        r"\bkpi\b", r"\boee\b", r"performance", r"availability",
        r"quality\s+rate", r"efficiency", r"metric",
        r"energy\s+consumption", r"cycle\s+time",
    ],
    Intent.LIST_TWINS: [
        r"list\s+(all\s+)?(the\s+)?twins",
        r"show\s+(all\s+)?(the\s+)?twins",
        r"all\s+twins", r"my\s+twins",
        r"what\s+twins", r"how\s+many\s+twins",
    ],
    Intent.GET_ALERTS: [
        r"alert", r"alarm", r"warning", r"fault",
        r"error", r"issue", r"problem", r"anomal", r"critical",
    ],
    Intent.DELETE_TWIN: [
        r"delete\s+(a\s+)?(digital\s+)?twin",
        r"remove\s+(a\s+)?(digital\s+)?twin",
    ],
}

COMPILED_PATTERNS = {
    intent: [re.compile(p, re.IGNORECASE) for p in patterns]
    for intent, patterns in INTENT_PATTERNS.items()
}


def classify_intent_rules(message: str) -> tuple[Intent, float]:
    """Rule-based intent classification fallback."""
    best_intent = Intent.GENERAL_QUERY
    best_score = 0.0
    for intent, patterns in COMPILED_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(message):
                matches = sum(1 for p in patterns if p.search(message))
                score = min(0.95, 0.75 + matches * 0.05)
                if score > best_score:
                    best_score = score
                    best_intent = intent
    if best_score > 0:
        return best_intent, best_score

    ml = message.lower()
    has_create_verb = any(v in ml for v in ("create", "add", "build", "generate", "ajoute", "créer", "creer"))
    has_asset_word = any(k in ml for k in ASSET_TYPE_ALIASES.keys()) or "machine" in ml
    if has_create_verb and has_asset_word:
        return Intent.CREATE_TWIN, 0.82

    return Intent.GENERAL_QUERY, 0.3


def extract_entities(message: str, intent: Intent) -> dict[str, Any]:
    """Extract entities from user message."""
    entities: dict[str, Any] = {}
    ml = message.lower()

    # Asset type
    for key, val in ASSET_TYPE_ALIASES.items():
        if key in ml:
            entities["type"] = val
            break
    entities.setdefault("type", "CNC")

    # Multi-machine batch extraction (e.g. "2 cnc and 1 robot")
    aliases_pattern = "|".join(sorted([re.escape(k) for k in ASSET_TYPE_ALIASES.keys()], key=len, reverse=True))
    batch_matches = re.findall(rf"(\d+)\s*(?:x\s*)?({aliases_pattern})s?\b", ml)
    if batch_matches:
        batch_specs: list[dict[str, Any]] = []
        for count_str, asset_token in batch_matches:
            token = asset_token.strip().lower()
            if token.endswith("s") and token[:-1] in ASSET_TYPE_ALIASES:
                token = token[:-1]
            asset_type = ASSET_TYPE_ALIASES.get(token)
            if not asset_type:
                continue
            batch_specs.append({"type": asset_type, "count": int(count_str)})

        if batch_specs:
            entities["batch"] = batch_specs
            entities["count"] = sum(item["count"] for item in batch_specs)
            entities["type"] = batch_specs[0]["type"]

    # Global count (e.g. "add 4 machines")
    if "count" not in entities:
        count_match = re.search(r"\b(\d+)\s*(machines?|twins?|assets?)\b", ml)
        if count_match:
            entities["count"] = int(count_match.group(1))

    # Floor
    m = re.search(r"floor\s*(\d+)", ml)
    if m: entities["floor"] = m.group(1)

    # Line
    m = re.search(r"line\s*([a-zA-Z0-9]+)", ml)
    if m: entities["line"] = m.group(1).upper()

    # Energy
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kwh|kw|kilowatt)", ml)
    if m: entities["energy"] = float(m.group(1))

    # Components
    m = re.search(r"(\d+)\s*(spindles?|components?|axes?|tools?|motors?)", ml)
    if m:
        entities["components"] = int(m.group(1))
        entities["component_type"] = m.group(2).rstrip("s")

    # Protocol
    if "opc" in ml: entities["protocol"] = "OPC-UA"
    elif "mqtt" in ml: entities["protocol"] = "MQTT"

    # Twin ID
    m = re.search(r"([A-Z]{2,}-\d+)", message)
    if m: entities["twin_id"] = m.group(1)

    return entities


# ═══════════════════════════════════════════════════════════
# CONVERSATION AGENT
# ═══════════════════════════════════════════════════════════

class ConversationAgent:
    """
    Agent 1 — Conversation Agent

    Permissions:
    - READ user input only
    - WRITE to message bus (Agent 2 inbox) only
    - NO direct database access, NO direct tool invocation
    """

    def __init__(self):
        self._settings = get_settings()
        self._llm_available = False
        self._llm_provider = None
        self._init_llm()
        self._session_counts: dict[str, list[float]] = {}

    def _init_llm(self):
        """Initialize LLM provider."""
        if self._settings.gemini_api_key:
            self._llm_provider = 'gemini'
            self._llm_available = True
            logger.info("LLM initialized: Gemini (gemini-1.5-flash)")
        elif self._settings.groq_api_key:
            self._llm_provider = 'groq'
            self._llm_available = True
            logger.info(f"LLM initialized: Groq ({self._settings.groq_model})")
        else:
            logger.info("No LLM API keys found. Using rule-based classification.")

    def _call_llm(self, prompt: str, json_mode: bool = False) -> str | None:
        """Call the LLM via HTTP (OpenAI-compatible)."""
        if not self._llm_provider:
            return None

        url = ""
        headers = {"Content-Type": "application/json"}
        body = {"messages": [{"role": "user", "content": prompt}]}

        if self._llm_provider == 'gemini':
            url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            headers["Authorization"] = f"Bearer {self._settings.gemini_api_key}"
            body["model"] = "gemini-2.5-flash"
        else:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers["Authorization"] = f"Bearer {self._settings.groq_api_key}"
            body["model"] = self._settings.groq_model

        if json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=15)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"LLM call failed ({self._llm_provider}): {e}")
            if 'resp' in locals() and hasattr(resp, 'text'):
                logger.warning(f"Response: {resp.text[:500]}")
            return None

    # ── rate limiting ────────────────────────────────────
    def _check_rate_limit(self, sid: str) -> bool:
        now = time.time()
        self._session_counts.setdefault(sid, [])
        self._session_counts[sid] = [t for t in self._session_counts[sid] if now - t < 60]
        if len(self._session_counts[sid]) >= self._settings.rate_limit_per_min:
            return False
        self._session_counts[sid].append(now)
        return True

    # ── Classification prompt ─────────────────────────────
    def _build_classify_prompt(self, message: str) -> str:
        return (
            "You are an intent classifier for a Manufacturing Digital Twin system.\n"
            "Classify the following user message into exactly ONE intent:\n"
            "CREATE_TWIN, QUERY_TWIN, GET_KPI, LIST_TWINS, GET_ALERTS, "
            "DELETE_TWIN, UPDATE_TWIN, GENERAL_QUERY\n\n"
            "Examples:\n"
            '- "Create a CNC machine on floor 2": {"intent": "CREATE_TWIN", "confidence": 0.9, "entities": {"type": "CNC", "floor": "2"}}\n'
            '- "Add a new floor with 2 lines and 3 machines": {"intent": "CREATE_TWIN", "confidence": 0.9, "entities": {"type": "floor", "lines": 2, "machines": 3}}\n'
            '- "How is the efficiency of line A?": {"intent": "GET_KPI", "confidence": 0.9, "entities": {"line": "A", "kpi": "efficiency"}}\n'
            '- "Show all my twins": {"intent": "LIST_TWINS", "confidence": 0.95, "entities": {}}\n'
            '- "hello": {"intent": "GENERAL_QUERY", "confidence": 0.9, "entities": {}}\n'
            '- "Explain how AI works": {"intent": "GENERAL_QUERY", "confidence": 0.95, "entities": {}}\n'
            '\n'
            f'User message: "{message}"\n\n'
            "Respond ONLY with JSON (no markdown):\n"
            '{"intent":"INTENT_NAME","confidence":0.0-1.0,"entities":{}}\n'
            "entities can include: type, floor, line, energy, components, protocol, twin_id, machines, lines"
        )

    def _classify_llm(self, message: str) -> tuple[Intent, float, dict]:
        """Classify intent using the configured LLM provider."""
        prompt = self._build_classify_prompt(message)
        txt = self._call_llm(prompt, json_mode=True)
        if txt:
            try:
                txt = txt.strip()
                txt = re.sub(r'^```json\s*', '', txt)
                txt = re.sub(r'\s*```$', '', txt)
                data = json.loads(txt)
                intent = Intent(data.get("intent", "GENERAL_QUERY"))
                confidence = float(data.get("confidence", 0.8))
                entities = data.get("entities", {})
                
                if not isinstance(entities, dict):
                    logger.warning(f"LLM returned invalid entities type: {type(entities)}. Resetting to empty dict.")
                    entities = {}

                return intent, confidence, entities
            except Exception as e:
                logger.warning(f"LLM classify parse failed: {e}. Raw: {txt[:200]}")
        # Fallback to rules
        intent, conf = classify_intent_rules(message)
        return intent, conf, extract_entities(message, intent)

    # ── main entry point ─────────────────────────────────
    def process_user_input(self, user_input: UserInput) -> IntentResult | str:
        start = time.time()
        message = user_input.user_message
        sid = user_input.session_id

        # Rate limit
        if not self._check_rate_limit(sid):
            log_agent_action(AGENT_ID, "rate_limit", "rate_limiter", sid,
                             success=False, duration_ms=(time.time()-start)*1000)
            return " Rate limit exceeded. Please wait before sending another message."

        # Sanitize
        message = sanitize_input(message, self._settings.max_input_tokens)

        # Prompt injection check
        safe, reason = check_prompt_injection(message)
        if not safe:
            log_agent_action(AGENT_ID, "injection_blocked", "security",
                             "[REDACTED]", success=False, reasoning_trace=reason,
                             duration_ms=(time.time()-start)*1000)
            return " Message flagged by security. Please rephrase."

        # PII detection (warn only)
        pii = detect_pii(message)
        if pii:
            log_agent_action(AGENT_ID, "pii_detected", "pii_detector",
                             reasoning_trace=json.dumps(pii))

        # Intent classification
        if self._llm_available:
            intent, conf, entities = self._classify_llm(message)
        else:
            intent, conf = classify_intent_rules(message)
            entities = extract_entities(message, intent)

        if intent == Intent.GENERAL_QUERY and self._llm_available:
            # Generate conversational response
            answer = self._chat_llm(message)
            if answer:
                # Return answer directly as string (API handles this as response)
                # Or we could wrap in IntentResult entities, but string is simpler
                # consistent with error messages.
                log_agent_action(
                    AGENT_ID, "chat_response", self._llm_provider or "llm", message, 
                    answer[:50]+"...", duration_ms=(time.time()-start)*1000
                )
                return answer

        # Merge rule entities for completeness
        rule_ents = extract_entities(message, intent)
        for k, v in rule_ents.items():
            if k not in entities or not entities[k]:
                entities[k] = v

        result = IntentResult(
            intent=intent, entities=entities, confidence=conf,
            session_id=sid, raw_message=message,
        )

        log_agent_action(
            AGENT_ID, "classify_intent",
            self._llm_provider or "rules",
            message, json.dumps(result.model_dump(), default=str),
            duration_ms=(time.time()-start)*1000,
            reasoning_trace=f"{intent.value} conf={conf:.2f}"
        )
        return result

    def _chat_llm(self, message: str) -> str | None:
        """Generate a conversational response for general queries."""
        prompt = (
            "You are a helpful AI assistant for a Manufacturing Digital Twin system called TwinForge.\n"
            "Answer the user's question concisely and helpfully.\n\n"
            f"User: {message}"
        )
        return self._call_llm(prompt, json_mode=False)

    def format_response(self, twin_result: TwinResult) -> str:
        return twin_result.explanation or "Operation completed."
