"""
Privilege Escalation Detector - Detects agents attempting to exceed their permissions.

Each agent in TWINFORGE has a defined set of allowed tools and channels.
This detector flags when an agent tries to:
1. Call tools outside its allowed set
2. Write to channels it shouldn't access
3. Access resources beyond its scope (e.g. other tenants' data)
4. Perform admin-level operations without authorization
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Each agent's allowed tools and channel permissions
AGENT_PERMISSIONS = {
    "agent_1": {
        "name": "agent-conversation",
        "allowed_tools": {
            "intent_classifier", "prompt_injection_filter", "response_formatter",
            "input_sanitizer", "rate_limiter",
        },
        "allowed_channels": {"agent_1_in", "agent_1_out", "orchestrator_in"},
        "can_write_db": False,
        "can_access_vault": False,
    },
    "agent_2": {
        "name": "agent-orchestrator",
        "allowed_tools": {
            "aas_creator", "kpi_engine", "rag_retriever", "smia_agent_spawner",
            "aas_validator",
        },
        "allowed_channels": {"orchestrator_in", "orchestrator_out", "agent_*_in"},
        "can_write_db": True,
        "can_access_vault": False,
    },
    "agent_3": {
        "name": "agent-data-iot",
        "allowed_tools": {
            "opcua_client", "mqtt_client", "mcp_client", "sensor_validator",
        },
        "allowed_channels": {"agent_3_in", "agent_3_out", "orchestrator_in"},
        "can_write_db": True,
        "can_access_vault": False,
    },
    "agent_4": {
        "name": "agent-verifier",
        "allowed_tools": {
            "kpi_validator", "source_verifier", "anomaly_detector", "schema_enforcer",
        },
        "allowed_channels": {"agent_4_in", "agent_4_out", "orchestrator_in"},
        "can_write_db": False,
        "can_access_vault": False,
    },
    "agent_5": {
        "name": "agent-security",
        "allowed_tools": {
            "prompt_injection_detector", "rag_poisoning_detector",
            "privilege_escalation_detector", "data_exfiltration_detector",
            "agent_spoofing_detector", "message_bus_monitor",
            "tool_usage_monitor", "anomaly_monitor",
            "alert_manager", "incident_logger",
        },
        "allowed_channels": {"*"},  # Security agent monitors all channels
        "can_write_db": True,
        "can_access_vault": True,
    },
}

# Operations that require elevated privileges
ADMIN_OPERATIONS = {
    "delete_aas", "drop_table", "truncate", "grant_permission",
    "revoke_permission", "modify_agent_config", "restart_agent",
    "update_signing_key", "vault_write", "modify_permissions",
}


class PrivilegeEscalationDetector:
    """
    Detects agents attempting to exceed their defined permissions.
    """

    def detect(self, payload: dict[str, Any], source_agent: str) -> dict:
        """
        Check if the source agent is attempting operations beyond its permissions.

        Relevant payload fields:
        - tool_name: tool being invoked
        - target_channel: channel being written to
        - operation: the operation being performed
        - target_agent: if trying to control another agent
        - target_tenant: if accessing cross-tenant data

        Args:
            payload: The message payload dict.
            source_agent: The agent ID performing the action.

        Returns:
            dict with threat_detected and details.
        """
        issues = []
        permissions = AGENT_PERMISSIONS.get(source_agent)

        if not permissions:
            # Unknown agent - handled by spoofing detector, skip here
            return {"threat_detected": False}

        # --- Check 1: Unauthorized tool usage ---
        tool_name = payload.get("tool_name", "")
        if tool_name and tool_name not in permissions["allowed_tools"]:
            issues.append({
                "check": "unauthorized_tool",
                "severity": "HIGH",
                "detail": (
                    f"Agent '{source_agent}' attempted to use tool '{tool_name}' "
                    f"which is not in its allowed set"
                ),
            })

        # --- Check 2: Unauthorized channel access ---
        target_channel = payload.get("target_channel", "")
        if target_channel:
            allowed = permissions["allowed_channels"]
            if "*" not in allowed and target_channel not in allowed:
                # Check wildcard patterns like "agent_*_in"
                matched = False
                for pattern in allowed:
                    if "*" in pattern:
                        import fnmatch
                        if fnmatch.fnmatch(target_channel, pattern):
                            matched = True
                            break
                if not matched:
                    issues.append({
                        "check": "unauthorized_channel",
                        "severity": "MEDIUM",
                        "detail": (
                            f"Agent '{source_agent}' attempted to access channel "
                            f"'{target_channel}' outside its allowed channels"
                        ),
                    })

        # --- Check 3: Admin operations without authorization ---
        operation = payload.get("operation", "")
        if operation and operation.lower() in ADMIN_OPERATIONS:
            if source_agent != "agent_5":  # Only security agent has admin rights
                issues.append({
                    "check": "admin_operation",
                    "severity": "CRITICAL",
                    "detail": (
                        f"Agent '{source_agent}' attempted admin operation "
                        f"'{operation}' without authorization"
                    ),
                })

        # --- Check 4: Unauthorized DB write ---
        if payload.get("db_write") and not permissions.get("can_write_db"):
            issues.append({
                "check": "unauthorized_db_write",
                "severity": "HIGH",
                "detail": f"Agent '{source_agent}' attempted database write without permission",
            })

        # --- Check 5: Unauthorized Vault access ---
        if payload.get("vault_access") and not permissions.get("can_access_vault"):
            issues.append({
                "check": "unauthorized_vault_access",
                "severity": "CRITICAL",
                "detail": f"Agent '{source_agent}' attempted Vault access without permission",
            })

        # --- Check 6: Cross-tenant data access ---
        target_tenant = payload.get("target_tenant", "")
        request_tenant = payload.get("tenant_id", "")
        if target_tenant and request_tenant and target_tenant != request_tenant:
            issues.append({
                "check": "cross_tenant_access",
                "severity": "CRITICAL",
                "detail": (
                    f"Agent '{source_agent}' attempted cross-tenant access: "
                    f"own tenant='{request_tenant}', target='{target_tenant}'"
                ),
            })

        if not issues:
            return {"threat_detected": False}

        severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        worst = max(issues, key=lambda i: severity_rank.get(i["severity"], 0))

        confidence_map = {"CRITICAL": 0.95, "HIGH": 0.9, "MEDIUM": 0.75, "LOW": 0.5}
        confidence = min(1.0, confidence_map.get(worst["severity"], 0.5) + 0.03 * (len(issues) - 1))

        all_details = "; ".join(i["detail"] for i in issues)
        action = "BLOCK" if worst["severity"] in ("CRITICAL", "HIGH") else "ALERT"

        logger.warning(
            f"Privilege escalation detected from {source_agent}: "
            f"severity={worst['severity']}, checks_failed={[i['check'] for i in issues]}"
        )

        return {
            "threat_detected": True,
            "threat_type": "PRIVILEGE_ESCALATION",
            "severity": worst["severity"],
            "confidence": round(confidence, 2),
            "details": all_details,
            "recommended_action": action,
        }
