"""
Incident Logger - Persists security incidents to structured logs and database.

Provides two layers of persistence:
1. Structured JSON logging (always available, no external deps)
2. PostgreSQL insertion (when DB is available)

Each incident gets a unique ID, timestamp, and full threat + request context.
"""

import asyncio
import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Separate structured logger for security incidents (JSON format)
incident_logger = logging.getLogger("twinforge.security.incidents")


class IncidentLogger:
    """
    Logs security incidents to structured logs and optionally to PostgreSQL.
    """

    def __init__(self, db_url: str = ""):
        self.db_url = db_url
        # In-memory recent incidents buffer (for API queries without DB)
        self._recent_incidents: list[dict[str, Any]] = []
        self._max_buffer = 1000
        self._db_pool = None
        self._db_initialized = False

    async def init_db(self):
        """Initialize PostgreSQL connection pool and create table if needed."""
        if not self.db_url:
            return
        try:
            import asyncpg
            self._db_pool = await asyncpg.create_pool(self.db_url, min_size=1, max_size=5)
            await self._create_table()
            self._db_initialized = True
            logger.info("PostgreSQL incident persistence initialized")
        except Exception as e:
            logger.warning(f"PostgreSQL unavailable, using in-memory only: {e}")

    async def _create_table(self):
        """Create the security_incidents table if it doesn't exist."""
        if not self._db_pool:
            return
        async with self._db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS security_incidents (
                    incident_id UUID PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL,
                    threat_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    confidence FLOAT,
                    details TEXT,
                    recommended_action TEXT,
                    source_agent TEXT,
                    event_type TEXT,
                    session_id TEXT,
                    tenant_id TEXT,
                    payload_summary TEXT
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_incidents_severity
                ON security_incidents(severity)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_incidents_timestamp
                ON security_incidents(timestamp)
            """)

    async def log(self, threat: dict[str, Any], request: Any = None):
        """
        Log a security incident.

        Args:
            threat: The threat detection result dict (from a detector).
            request: The original SecurityEventRequest (optional, for context).
        """
        incident_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Build the incident record
        incident = {
            "incident_id": incident_id,
            "timestamp": now.isoformat(),
            "threat_type": threat.get("threat_type", "UNKNOWN"),
            "severity": threat.get("severity", "UNKNOWN"),
            "confidence": threat.get("confidence", 0.0),
            "details": threat.get("details", ""),
            "recommended_action": threat.get("recommended_action", "LOG"),
        }

        # Add request context if available
        if request is not None:
            incident["source_agent"] = getattr(request, "source_agent", "")
            incident["event_type"] = getattr(request, "event_type", "")
            incident["session_id"] = getattr(request, "session_id", "")
            incident["tenant_id"] = getattr(request, "tenant_id", "")
            # Store payload summary (truncate to avoid huge logs)
            payload = getattr(request, "payload", {})
            payload_str = json.dumps(payload, default=str)
            if len(payload_str) > 2000:
                payload_str = payload_str[:2000] + "...(truncated)"
            incident["payload_summary"] = payload_str

        # 1. Structured log output
        incident_logger.warning(json.dumps(incident, default=str))

        # 2. Also log to standard logger for console visibility
        logger.warning(
            f"SECURITY INCIDENT [{incident['severity']}] "
            f"{incident['threat_type']}: {incident['details'][:200]} "
            f"(id={incident_id})"
        )

        # 3. Buffer in memory
        self._recent_incidents.append(incident)
        if len(self._recent_incidents) > self._max_buffer:
            self._recent_incidents = self._recent_incidents[-self._max_buffer:]

        # 4. Persist to PostgreSQL (fire-and-forget)
        if self._db_initialized:
            asyncio.create_task(self._persist_to_db(incident))

    async def _persist_to_db(self, incident: dict[str, Any]):
        """Insert incident into PostgreSQL."""
        if not self._db_pool:
            return
        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO security_incidents
                    (incident_id, timestamp, threat_type, severity, confidence,
                     details, recommended_action, source_agent, event_type,
                     session_id, tenant_id, payload_summary)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    uuid.UUID(incident["incident_id"]),
                    datetime.fromisoformat(incident["timestamp"]),
                    incident.get("threat_type", ""),
                    incident.get("severity", ""),
                    incident.get("confidence", 0.0),
                    incident.get("details", ""),
                    incident.get("recommended_action", ""),
                    incident.get("source_agent", ""),
                    incident.get("event_type", ""),
                    incident.get("session_id", ""),
                    incident.get("tenant_id", ""),
                    incident.get("payload_summary", ""),
                )
        except Exception as e:
            logger.error(f"Failed to persist incident to DB: {e}")

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent incidents from the in-memory buffer."""
        return self._recent_incidents[-limit:]

    def get_by_severity(self, severity: str) -> list[dict[str, Any]]:
        """Filter recent incidents by severity level."""
        return [
            i for i in self._recent_incidents
            if i.get("severity") == severity
        ]

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics of logged incidents."""
        total = len(self._recent_incidents)
        by_severity: dict[str, int] = {}
        by_type: dict[str, int] = {}

        for incident in self._recent_incidents:
            sev = incident.get("severity", "UNKNOWN")
            by_severity[sev] = by_severity.get(sev, 0) + 1
            ttype = incident.get("threat_type", "UNKNOWN")
            by_type[ttype] = by_type.get(ttype, 0) + 1

        return {
            "total_incidents": total,
            "by_severity": by_severity,
            "by_type": by_type,
            "buffer_capacity": f"{total}/{self._max_buffer}",
            "db_connected": self._db_initialized,
        }
