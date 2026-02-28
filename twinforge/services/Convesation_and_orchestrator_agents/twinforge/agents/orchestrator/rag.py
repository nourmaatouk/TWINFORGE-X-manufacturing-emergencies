"""
TWINFORGE — RAG (Retrieval-Augmented Generation) module.
Uses an in-memory document store for knowledge grounding.
ChromaDB can be plugged in when available.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger("twinforge.rag")


# ════════════════════════════════════════════════════════════
# KNOWLEDGE BASE DOCUMENTS
# ════════════════════════════════════════════════════════════

KNOWLEDGE_BASE: list[dict[str, str]] = [
    {
        "id": "cnc_machine_spec",
        "title": "CNC Machine Specifications",
        "content": """CNC (Computer Numerical Control) machines are automated manufacturing equipment
that use computer programs to control machining tools. Key specifications include:
- Spindle Speed: Typically 4,000-15,000 RPM for standard CNC mills
- Power Rating: 15-75 kWh depending on size and type
- Axes: 3-axis (X,Y,Z), 4-axis, or 5-axis configurations
- Tolerance: ±0.005mm to ±0.025mm depending on machine class
- Components: Spindle, tool changer, coolant system, chip conveyor
- Common types: Milling, Turning, Drilling, Grinding, EDM""",
    },
    {
        "id": "oee_methodology",
        "title": "OEE Calculation Methodology",
        "content": """OEE (Overall Equipment Effectiveness) is the gold standard for measuring
manufacturing productivity. Formula: OEE = Availability × Performance × Quality

Availability = (Run Time / Planned Production Time) × 100
- Accounts for: Equipment failures, setup/adjustments, material shortages

Performance = (Ideal Cycle Time × Total Pieces) / Run Time × 100  
- Accounts for: Small stops, reduced speed, idling

Quality = (Good Pieces / Total Pieces) × 100
- Accounts for: Defects, rework, startup rejects

World-class OEE benchmarks:
- OEE > 85%: World-class
- OEE 65-85%: Typical
- OEE < 65%: Improvement needed

Common OEE losses (Six Big Losses):
1. Equipment breakdown (Availability)
2. Setup & adjustment (Availability)
3. Idling & minor stops (Performance)
4. Reduced speed (Performance)
5. Process defects (Quality)
6. Reduced yield / startup losses (Quality)""",
    },
    {
        "id": "aas_standard",
        "title": "Asset Administration Shell (AAS) Standard",
        "content": """The Asset Administration Shell (AAS) is the standardized digital representation
of an asset in Industry 4.0, defined by IDTA (Industrial Digital Twin Association).

Structure:
- AAS Shell: Container for all information about an asset
- Asset Information: Global asset ID, kind (Instance/Type)
- Submodels: Modular containers for specific aspects:
  - Nameplate (IDTA 02006-2-0): Manufacturer info, serial numbers
  - TechnicalData (IDTA 02003-1-2): Technical specifications
  - OperationalData: Runtime operational metrics
  - Documentation: Manuals, certificates
  - Maintenance: Maintenance schedules and records

Twin Levels (hierarchical):
1. Component Twin: Individual part (e.g., spindle, motor)
2. Asset Twin: Complete machine (e.g., CNC machine)
3. System Twin: Production line or cell
4. Process Twin: Entire manufacturing process/workflow

Serialization formats: JSON, XML, AASX (ZIP package)""",
    },
    {
        "id": "predictive_maintenance",
        "title": "Predictive Maintenance Strategies",
        "content": """Predictive maintenance uses sensor data analysis to predict equipment
failures before they occur. Key indicators:

Temperature monitoring:
- Normal: 50-75°C operating range
- Warning: >80°C sustained
- Critical: >90°C immediate attention

Vibration analysis:
- Good: <4.5 mm/s RMS
- Alert: 4.5-7.0 mm/s
- Danger: >7.0 mm/s (bearing/alignment issues)

Tool wear progression:
- New: 0-30% wear
- Normal: 30-65% wear  
- End of life warning: 65-85% wear
- Critical replacement: >85% wear

Maintenance scheduling priorities:
1. Safety-critical items first
2. Production bottleneck equipment
3. High-value assets
4. Routine maintenance items""",
    },
    {
        "id": "industry40_reference",
        "title": "Industry 4.0 / RAMI 4.0 Reference",
        "content": """Industry 4.0 (Fourth Industrial Revolution) integrates:
- Cyber-Physical Systems (CPS)
- Internet of Things (IoT)
- Cloud Computing
- Artificial Intelligence

RAMI 4.0 (Reference Architecture Model):
- Layers: Asset, Integration, Communication, Information, Functional, Business
- Life Cycle: Development, Production, Maintenance, Disposal
- Hierarchy: Product, Field Device, Control Device, Station, Work Center, Enterprise

Key protocols:
- OPC-UA: Unified Architecture for machine-to-machine communication
- MQTT: Lightweight messaging for IoT sensor data
- REST/HTTP: Web service integration

CSS Model (Capability-Skill-Service):
- Capability: What the system CAN do
- Skill: HOW the system does it (executable behavior)
- Service: Interface to access the skill""",
    },
    {
        "id": "smia_agent_model",
        "title": "SMIA Agent Architecture",
        "content": """SMIA (Smart Manufacturing Interoperable Agent) extends the AAS with
agent-based capabilities following the CSS (Capability-Skill-Service) model.

Agent Types:
- Asset Agent: Manages a single physical asset's digital twin
- System Agent: Coordinates multiple asset agents
- Process Agent: Orchestrates manufacturing workflows

Agent Capabilities:
- Self-monitoring: Continuous sensor data validation
- Self-optimization: KPI-driven parameter adjustment
- Self-configuration: Dynamic adaptation to production changes
- Fault detection: Anomaly detection and alerting

Communication:
- FIPA ACL (Agent Communication Language) compatible
- Publish/Subscribe for sensor streams
- Request/Response for commands
- Blackboard pattern for shared state""",
    },
]


class RAGRetriever:
    """
    Simple in-memory RAG retriever.
    Uses keyword matching for demonstration.
    Can be replaced with ChromaDB vector search in production.
    """
    
    def __init__(self):
        self._documents = {doc["id"]: doc for doc in KNOWLEDGE_BASE}
    
    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, str]]:
        """Retrieve relevant documents for a query using keyword scoring."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        scored = []
        for doc in self._documents.values():
            content_lower = (doc["title"] + " " + doc["content"]).lower()
            # Simple keyword overlap scoring
            score = 0
            for word in query_words:
                if len(word) > 2:
                    count = content_lower.count(word)
                    score += count
            scored.append((score, doc))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Return top-k with score > 0
        results = []
        for score, doc in scored[:top_k]:
            if score > 0:
                results.append({
                    "id": doc["id"],
                    "title": doc["title"],
                    "content": doc["content"],
                    "relevance_score": min(score / 10.0, 1.0),
                })
        
        return results
    
    def get_grounding_context(self, query: str, max_chars: int = 2000) -> str:
        """Get concatenated grounding context for LLM prompts."""
        docs = self.retrieve(query, top_k=3)
        context_parts = []
        total_chars = 0
        
        for doc in docs:
            chunk = f"[{doc['title']}]\n{doc['content']}\n"
            if total_chars + len(chunk) > max_chars:
                break
            context_parts.append(chunk)
            total_chars += len(chunk)
        
        return "\n".join(context_parts) if context_parts else "No relevant knowledge found."
