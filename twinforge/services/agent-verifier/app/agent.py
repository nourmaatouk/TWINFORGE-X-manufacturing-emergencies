"""
Verifier Agent - Critic that validates outputs from other agents.
"""

import logging
from datetime import datetime, timezone

from app.models.schemas import AgentRequest, AgentResponse
from app.tools.kpi_validator import KPIValidator
from app.tools.source_verifier import SourceVerifier
from app.tools.anomaly_detector import AnomalyDetector
from app.tools.schema_enforcer import SchemaEnforcer
from app.config import settings

logger = logging.getLogger(__name__)


class VerifierAgent:
    """Agent 4: Validates and verifies outputs from Agents 2 and 3."""

    def __init__(self):
        self.kpi_validator = KPIValidator()
        self.source_verifier = SourceVerifier()
        self.anomaly_detector = AnomalyDetector()
        self.schema_enforcer = SchemaEnforcer()

    async def initialize(self):
        logger.info(f"Initializing {settings.AGENT_NAME} agent...")

    async def shutdown(self):
        logger.info(f"Shutting down {settings.AGENT_NAME} agent...")

    async def process(self, request: AgentRequest) -> AgentResponse:
        """Verify the output from another agent."""
        verification_type = request.payload.get("verification_type", "schema")

        if verification_type == "kpi":
            result = self.kpi_validator.validate(request.payload)
        elif verification_type == "source":
            result = self.source_verifier.verify(request.payload)
        elif verification_type == "anomaly":
            result = self.anomaly_detector.detect(request.payload)
        else:
            result = self.schema_enforcer.enforce(request.payload)

        return AgentResponse(
            session_id=request.session_id,
            agent_id=settings.AGENT_ID,
            status="success",
            payload={"verification": result},
            timestamp=datetime.now(timezone.utc),
        )
