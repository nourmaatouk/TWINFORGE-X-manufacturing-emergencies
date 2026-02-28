"""
TWINFORGE — Agent 2: Twin Orchestrator Agent (SMIA Core).
Receives structured intent from Agent 1, orchestrates twin creation,
computes KPIs, detects faults, manages AAS submodels, and generates
explainable reasoning traces.
"""
from __future__ import annotations
import json
import os
import time
import uuid
import logging
from datetime import datetime
from typing import Any

from twinforge.core.schemas import (
    IntentResult, Intent, TwinLevel, TwinResult, TwinEntry,
    KPIData, Alert, AlertSeverity, DataRequest, DataResponse
)
from twinforge.core.logging_config import log_agent_action
from twinforge.agents.orchestrator.aas_manager import AASManager
from twinforge.agents.orchestrator.kpi_engine import KPIEngine
from twinforge.agents.orchestrator.rag import RAGRetriever
from twinforge.agents.orchestrator.tft_engine import TFTPredictionEngine
from twinforge.agents.orchestrator.smia_spawner import SMIASpawner

logger = logging.getLogger("twinforge.agent.orchestrator")

AGENT_ID = "agent_2_orchestrator"

def _parse_numeric(val, default=0.0) -> float:
    """Safely convert a value to float, stripping unit suffixes like 'kwh', 'kw', etc."""
    if val is None:
        return default
    s = str(val).strip().lower()
    # Strip common unit suffixes
    for suffix in ('kwh', 'kw', 'mwh', 'mw', 'wh', 'w', 'kva', 'rpm', 'hz', 'bar', '%'):
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
            break
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


class TwinOrchestratorAgent:
    """
    Agent 2 — Twin Orchestrator Agent
    
    Permissions:
    - READ/WRITE AAS store (scoped to current session tenant)
    - READ from Agent 3 data bus (sensor feeds, logs)
    - WRITE computed twins to AAS store
    - WRITE response to Agent 1 message bus
    - NO direct user access
    - NO external HTTP calls
    """
    
    def __init__(self):
        self._aas_manager = AASManager()
        self._kpi_engine = KPIEngine()
        self._rag = RAGRetriever()
        self._tft = TFTPredictionEngine()
        self._smia_spawner = SMIASpawner(
            kpi_engine=self._kpi_engine,
            tft_engine=self._tft,
        )
        self._twin_store: dict[str, TwinEntry] = {}
        self._twin_counter = 0
        self._seed_default_twins()

    def _default_profile_for_type(self, asset_type: str) -> dict[str, Any]:
        profiles = {
            "CNC": {"components": 3, "component_type": "spindle", "protocol": "OPC-UA", "energy": 45},
            "Robot": {"components": 6, "component_type": "joint", "protocol": "MQTT", "energy": 32},
            "Conveyor": {"components": 8, "component_type": "roller", "protocol": "MQTT", "energy": 20},
            "Press": {"components": 2, "component_type": "cylinder", "protocol": "OPC-UA", "energy": 52},
            "Lathe": {"components": 2, "component_type": "spindle", "protocol": "OPC-UA", "energy": 40},
            "Mill": {"components": 3, "component_type": "axis", "protocol": "OPC-UA", "energy": 48},
            "Drill": {"components": 2, "component_type": "tool", "protocol": "OPC-UA", "energy": 26},
        }
        return profiles.get(asset_type, {"components": 3, "component_type": "component", "protocol": "OPC-UA", "energy": 35})

    def _apply_type_defaults(self, entities: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(entities)
        asset_type = str(normalized.get("type", "CNC"))
        profile = self._default_profile_for_type(asset_type)

        if "components" not in normalized or not normalized.get("components"):
            normalized["components"] = profile["components"]
        if "component_type" not in normalized or not normalized.get("component_type"):
            normalized["component_type"] = profile["component_type"]
        if "protocol" not in normalized or not normalized.get("protocol"):
            normalized["protocol"] = profile["protocol"]
        if "energy" not in normalized and "energy_kwh" not in normalized:
            normalized["energy"] = profile["energy"]

        return normalized

    def _expand_create_specs(self, entities: dict[str, Any]) -> list[dict[str, Any]]:
        batch = entities.get("batch")
        base = dict(entities)

        specs: list[dict[str, Any]] = []
        if isinstance(batch, list) and batch:
            for item in batch:
                item_type = item.get("type", base.get("type", "CNC"))
                item_count = max(1, min(int(item.get("count", 1)), 20))
                for _ in range(item_count):
                    spec = dict(base)
                    spec["type"] = item_type
                    spec.pop("batch", None)
                    spec.pop("count", None)
                    specs.append(self._apply_type_defaults(spec))
            return specs

        total = max(1, min(int(base.get("count", 1)), 20))
        base.pop("batch", None)
        base.pop("count", None)
        base = self._apply_type_defaults(base)
        for _ in range(total):
            specs.append(dict(base))
        return specs

    def _aggregate_batch_result(self, results: list[TwinResult]) -> TwinResult:
        if not results:
            return TwinResult(
                twin_id="batch-0",
                twin_level=TwinLevel.SYSTEM,
                explanation="No twins were created.",
                reasoning_trace=["Batch create produced no results"],
            )

        count = len(results)
        avg_availability = round(sum(r.kpis.availability for r in results) / count, 1)
        avg_performance = round(sum(r.kpis.performance for r in results) / count, 1)
        avg_quality = round(sum(r.kpis.quality for r in results) / count, 1)
        avg_oee = round(sum(r.kpis.oee for r in results) / count, 1)
        avg_energy = round(sum(r.kpis.energy_consumption_kwh for r in results) / count, 1)
        avg_cycle = round(sum(r.kpis.cycle_time_seconds for r in results) / count, 1)

        aggregated_kpis = KPIData(
            availability=avg_availability,
            performance=avg_performance,
            quality=avg_quality,
            oee=avg_oee,
            energy_consumption_kwh=avg_energy,
            cycle_time_seconds=avg_cycle,
        )
        all_alerts = [a for r in results for a in r.alerts]
        created_ids = [r.twin_id for r in results]

        return TwinResult(
            twin_id=created_ids[-1],
            twin_level=TwinLevel.SYSTEM,
            kpis=aggregated_kpis,
            alerts=all_alerts,
            aas_reference=f"batch:{count}",
            explanation=(
                f"✅ Created **{count} digital twins** in one request: {', '.join(created_ids)}. "
                f"Average OEE: **{avg_oee}%**."
            ),
            reasoning_trace=[f"Batch create completed for {count} twins"],
            components=[{"twin_id": r.twin_id, "component_count": len(r.components)} for r in results],
        )

    def _seed_default_twins(self):
        if os.getenv("TF_SEED_ON_START", "1") != "1":
            return
        if self._twin_store:
            return

        seed_entities = {
            "batch": [
                {"type": "CNC", "count": 2},
                {"type": "Robot", "count": 2},
                {"type": "Conveyor", "count": 1},
                {"type": "Press", "count": 1},
            ],
            "floor": "1",
            "line": "A",
        }
        try:
            seed_intent = IntentResult(
                intent=Intent.CREATE_TWIN,
                entities=seed_entities,
                confidence=1.0,
                session_id="seed",
                raw_message="seed default machines",
            )
            self.process_create_twin(seed_intent, None)
            logger.info("Seeded default machine dataset on startup")
        except Exception as exc:
            logger.warning(f"Failed to seed default machines: {exc}")
    
    # ═══════════════════════════════════════════════════════
    # TOOL: AAS Creator
    # ═══════════════════════════════════════════════════════
    
    def aas_creator(
        self,
        twin_id: str,
        twin_level: TwinLevel,
        entities: dict[str, Any],
        sensor_data: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """Create AAS shell + submodels for a new digital twin."""
        start = time.time()
        
        components = entities.get("components", [])
        if isinstance(components, dict):
            # LLM returned a dict like {"spindle_1": ...} — convert to list
            components = [{"name": k, "type": k.split("_")[0], "status": "operational", "health": 95} for k in components]
        elif isinstance(components, int):
            # User specified count, generate component list
            comp_type = entities.get("component_type", "spindle")
            components = [
                {"name": f"{comp_type}_{i+1}", "type": comp_type, "status": "operational", "health": 95}
                for i in range(components)
            ]
        elif isinstance(components, str):
            try:
                count = int(components)
                comp_type = entities.get("component_type", "spindle")
                components = [
                    {"name": f"{comp_type}_{i+1}", "type": comp_type, "status": "operational", "health": 95}
                    for i in range(count)
                ]
            except ValueError:
                components = [{"name": components, "type": components, "status": "operational", "health": 95}]
        
        aas = self._aas_manager.create_twin_aas(
            twin_id=twin_id,
            twin_level=twin_level,
            asset_type=entities.get("type", entities.get("asset_type", "CNC")),
            name=entities.get("name", twin_id),
            floor=str(entities.get("floor", "")),
            line=str(entities.get("line", "A")),
            energy_kwh=_parse_numeric(entities.get("energy", entities.get("energy_kwh", 0))),
            components=components,
            sensor_data=sensor_data,
        )
        
        # Validate all submodels
        validation_results = []
        for sm in aas.submodels:
            valid, errors = self._aas_manager.validate_submodel(sm)
            validation_results.append({"submodel": sm.id_short, "valid": valid, "errors": errors})
        
        log_agent_action(
            agent_id=AGENT_ID, action="create_aas", tool_used="aas_creator",
            input_data=twin_id, duration_ms=(time.time() - start) * 1000,
            reasoning_trace=f"Created AAS with {len(aas.submodels)} submodels for {twin_id}"
        )
        
        return {
            "aas_id": aas.id,
            "twin_id": twin_id,
            "submodels": [sm.id_short for sm in aas.submodels],
            "validation": validation_results,
            "aas_data": aas.to_dict(),
        }
    
    # ═══════════════════════════════════════════════════════
    # TOOL: KPI Engine
    # ═══════════════════════════════════════════════════════
    
    def compute_kpis(
        self, 
        sensor_data: dict[str, Any],
        asset_type: str = "CNC",
        energy_kwh: float = 0.0,
    ) -> KPIData:
        """Compute KPIs from sensor data."""
        start = time.time()
        kpis = self._kpi_engine.compute_kpis_from_sensors(sensor_data, asset_type, energy_kwh)
        
        log_agent_action(
            agent_id=AGENT_ID, action="compute_kpis", tool_used="kpi_engine",
            duration_ms=(time.time() - start) * 1000,
            reasoning_trace=f"Computed OEE={kpis.oee}% (A={kpis.availability}% P={kpis.performance}% Q={kpis.quality}%)"
        )
        return kpis
    
    # ═══════════════════════════════════════════════════════
    # TOOL: Fault Detector
    # ═══════════════════════════════════════════════════════
    
    def detect_faults(
        self,
        sensor_data: dict[str, Any],
        anomalies: list = None,
    ) -> list[Alert]:
        """Detect faults from sensor data and convert to alerts."""
        start = time.time()
        faults = self._kpi_engine.detect_faults(sensor_data, anomalies)
        
        alerts = []
        for fault in faults:
            alerts.append(Alert(
                alert_id=f"ALERT-{uuid.uuid4().hex[:8].upper()}",
                asset_id="current",
                severity=AlertSeverity(fault.get("severity", "WARNING")),
                message=fault.get("message", "Unknown fault"),
            ))
        
        log_agent_action(
            agent_id=AGENT_ID, action="detect_faults", tool_used="fault_detector",
            duration_ms=(time.time() - start) * 1000,
            reasoning_trace=f"Detected {len(alerts)} faults/alerts"
        )
        return alerts
    
    # ═══════════════════════════════════════════════════════
    # TOOL: SMIA Agent Spawner
    # ═══════════════════════════════════════════════════════
    
    def smia_agent_spawner(self, twin_id: str, twin_level: TwinLevel) -> dict[str, Any]:
        """Spawn a SMIA agent for the twin using SPADE (or simulated fallback)."""
        start = time.time()
        agent_info = self._smia_spawner.spawn(twin_id, twin_level.value)

        log_agent_action(
            agent_id=AGENT_ID, action="spawn_smia_agent", tool_used="smia_agent_spawner",
            input_data=twin_id, duration_ms=(time.time() - start) * 1000,
            reasoning_trace=(
                f"Spawned SMIA {twin_level.value} agent for {twin_id} "
                f"[{agent_info.get('runtime', 'unknown')} mode, "
                f"{len(agent_info.get('behaviours', []))} behaviours, "
                f"{len(agent_info.get('services', []))} services]"
            ),
        )
        return agent_info
    
    # ═══════════════════════════════════════════════════════
    # TOOL: RAG Retriever
    # ═══════════════════════════════════════════════════════
    
    def rag_retriever(self, query: str) -> list[dict]:
        """Query RAG knowledge base for grounding."""
        start = time.time()
        results = self._rag.retrieve(query)
        
        log_agent_action(
            agent_id=AGENT_ID, action="rag_retrieve", tool_used="rag_retriever",
            input_data=query, duration_ms=(time.time() - start) * 1000,
            reasoning_trace=f"Retrieved {len(results)} documents for grounding"
        )
        return results
    
    # ═══════════════════════════════════════════════════════
    # MAIN ORCHESTRATION METHODS
    # ═══════════════════════════════════════════════════════
    
    def _generate_twin_id(self, entities: dict) -> str:
        """Generate a unique twin ID."""
        self._twin_counter += 1
        asset_type = entities.get("type", entities.get("asset_type", "ASSET"))
        return f"{asset_type.upper()}-{self._twin_counter:02d}"
    
    def _determine_twin_level(self, entities: dict) -> TwinLevel:
        """Determine the twin level from entities."""
        explicit = entities.get("twin_level", "").lower()
        if explicit:
            for level in TwinLevel:
                if level.value.lower() == explicit:
                    return level
        
        components = entities.get("components", 0)
        if isinstance(components, list):
            components = len(components)
        elif isinstance(components, dict):
            components = len(components)
        elif isinstance(components, str):
            try:
                components = int(components)
            except ValueError:
                components = 1
        
        if isinstance(components, int) and components > 0:
            return TwinLevel.ASSET
        return TwinLevel.ASSET  # Default
    
    def process_create_twin(
        self,
        intent_result: IntentResult,
        data_response: DataResponse = None,
    ) -> TwinResult:
        """Process CREATE_TWIN intent."""
        start = time.time()
        reasoning = []
        entities = intent_result.entities

        expanded_specs = self._expand_create_specs(entities)
        if len(expanded_specs) > 1:
            results: list[TwinResult] = []
            for idx, spec in enumerate(expanded_specs, start=1):
                spec = dict(spec)
                spec.setdefault("name", f"{spec.get('type', 'ASSET')}-{idx}")
                single_intent = IntentResult(
                    intent=Intent.CREATE_TWIN,
                    entities=spec,
                    confidence=intent_result.confidence,
                    session_id=intent_result.session_id,
                    raw_message=intent_result.raw_message,
                )
                results.append(self.process_create_twin(single_intent, data_response))

            return self._aggregate_batch_result(results)

        entities = self._apply_type_defaults(entities)
        
        # Step 1: RAG lookup for context
        query = f"{entities.get('type', 'machine')} digital twin specifications"
        rag_docs = self.rag_retriever(query)
        reasoning.append(f"RAG lookup: found {len(rag_docs)} relevant documents")
        
        # Step 2: Determine twin level and ID
        twin_level = self._determine_twin_level(entities)
        twin_id = self._generate_twin_id(entities)
        reasoning.append(f"Twin level: {twin_level.value}, ID: {twin_id}")
        
        # Step 3: Spawn SMIA agent
        smia_info = self.smia_agent_spawner(twin_id, twin_level)
        reasoning.append(f"Spawned SMIA agent: {smia_info['agent_name']}")
        
        # Step 4: Get sensor data
        sensor_data = {}
        anomalies = []
        if data_response:
            sensor_data = data_response.sensor_data
            anomalies = data_response.anomalies
            reasoning.append(f"Sensor data received: {len(sensor_data)} channels, {len(anomalies)} anomalies")
        
        # Step 5: Create AAS
        aas_result = self.aas_creator(twin_id, twin_level, entities, sensor_data)
        reasoning.append(f"AAS created with {len(aas_result['submodels'])} submodels: {', '.join(aas_result['submodels'])}")
        
        # Step 6: Compute KPIs
        energy = _parse_numeric(entities.get("energy", entities.get("energy_kwh", 0)))
        kpis = self.compute_kpis(sensor_data, entities.get("type", "CNC"), energy)
        self._kpi_engine.store_baseline(twin_id, kpis)
        reasoning.append(f"KPIs computed: OEE={kpis.oee}%")
        
        # Step 7: Detect faults
        alerts = self.detect_faults(sensor_data, anomalies)
        reasoning.append(f"Fault detection: {len(alerts)} alerts")
        
        # Step 7b: Record sensor data for TFT prediction engine
        if sensor_data:
            self._tft.record_sensors(twin_id, sensor_data)
            reasoning.append("TFT prediction engine: sensor baseline recorded")
        
        # Step 8: Build components list
        components_list = entities.get("components", [])
        if isinstance(components_list, dict):
            components_list = [{"name": k, "type": k.split("_")[0]} for k in components_list]
        elif isinstance(components_list, int):
            comp_type = entities.get("component_type", "spindle")
            components_list = [
                {"name": f"{comp_type}_{i+1}", "type": comp_type}
                for i in range(components_list)
            ]
        elif isinstance(components_list, str):
            try:
                count = int(components_list)
                comp_type = entities.get("component_type", "spindle")
                components_list = [
                    {"name": f"{comp_type}_{i+1}", "type": comp_type}
                    for i in range(count)
                ]
            except ValueError:
                components_list = [{"name": components_list, "type": components_list}]
        
        # Step 9: Store twin
        twin_entry = TwinEntry(
            twin_id=twin_id,
            twin_level=twin_level,
            asset_type=entities.get("type", "CNC"),
            name=entities.get("name", twin_id),
            floor=str(entities.get("floor", "")),
            line=str(entities.get("line", "A")),
            protocol=entities.get("protocol", "OPC-UA"),
            energy_kwh=energy,
            components=components_list,
            kpis=kpis,
            alerts=alerts,
            aas_reference=aas_result["aas_id"],
            session_id=intent_result.session_id,
        )
        self._twin_store[twin_id] = twin_entry
        reasoning.append(f"Twin {twin_id} stored successfully")
        
        # Build explanation
        floor_info = f" on Floor {entities.get('floor', 'N/A')}" if entities.get('floor') else ""
        line_info = f", Line {entities.get('line', 'A')}" if entities.get('line') else ", Line A"
        comp_info = f" {len(components_list)} components modeled." if components_list else ""
        
        explanation = (
            f"✅ Digital Twin **{twin_id}** created{floor_info}{line_info}. "
            f"{twin_level.value}-level twin.{comp_info} "
            f"OEE baseline: **{kpis.oee}%**. "
            f"Energy model: {energy} kWh/h. "
            f"{'Live OPC-UA stream active.' if entities.get('protocol', '').upper() in ('OPCUA', 'OPC-UA') else 'Sensor monitoring active.'}"
        )
        
        if alerts:
            explanation += f"\n⚠️ {len(alerts)} active alert(s) detected."
        
        return TwinResult(
            twin_id=twin_id,
            twin_level=twin_level,
            kpis=kpis,
            alerts=alerts,
            aas_reference=aas_result["aas_id"],
            explanation=explanation,
            reasoning_trace=reasoning,
            components=components_list,
        )
    
    def process_query_twin(self, intent_result: IntentResult, data_response: DataResponse = None) -> TwinResult:
        """Process QUERY_TWIN intent."""
        entities = intent_result.entities
        twin_id = entities.get("twin_id", "")
        
        # Search by ID or partial match
        twin = self._twin_store.get(twin_id)
        if not twin:
            for tid, entry in self._twin_store.items():
                if twin_id.lower() in tid.lower() or twin_id.lower() in entry.name.lower():
                    twin = entry
                    twin_id = tid
                    break
        
        if not twin:
            return TwinResult(
                twin_id=twin_id or "unknown",
                twin_level=TwinLevel.ASSET,
                explanation=f"❌ Twin '{twin_id}' not found. Use 'List all twins' to see available twins.",
                reasoning_trace=["Twin lookup failed: ID not found in store"],
            )
        
        if data_response and data_response.sensor_data:
            twin.kpis = self.compute_kpis(data_response.sensor_data, twin.asset_type, twin.energy_kwh)
            twin.alerts = self.detect_faults(data_response.sensor_data, data_response.anomalies)
            self._tft.record_sensors(twin.twin_id, data_response.sensor_data)

        return TwinResult(
            twin_id=twin.twin_id,
            twin_level=twin.twin_level,
            kpis=twin.kpis,
            alerts=twin.alerts,
            aas_reference=twin.aas_reference,
            explanation=f"📊 Twin **{twin.twin_id}** ({twin.asset_type}, {twin.twin_level.value}-level)\n"
                       f"Floor: {twin.floor}, Line: {twin.line}\n"
                       f"OEE: **{twin.kpis.oee}%** | Availability: {twin.kpis.availability}% | "
                       f"Performance: {twin.kpis.performance}% | Quality: {twin.kpis.quality}%\n"
                       f"Energy: {twin.energy_kwh} kWh/h | Protocol: {twin.protocol}\n"
                       f"Components: {len(twin.components)} | Alerts: {len(twin.alerts)}",
            reasoning_trace=[f"Retrieved twin {twin.twin_id} from store"],
            components=twin.components,
        )
    
    def process_get_kpi(self, intent_result: IntentResult, data_response: DataResponse = None) -> TwinResult:
        """Process GET_KPI intent."""
        entities = intent_result.entities
        twin_id = entities.get("twin_id", "")
        
        # Find twin
        twin = self._twin_store.get(twin_id)
        if not twin:
            for tid, entry in self._twin_store.items():
                if twin_id.lower() in tid.lower():
                    twin = entry
                    twin_id = tid
                    break
        
        if not twin:
            # Compute fresh KPIs from sensor data if available
            if data_response:
                kpis = self.compute_kpis(data_response.sensor_data)
                return TwinResult(
                    twin_id=twin_id or "live",
                    twin_level=TwinLevel.ASSET,
                    kpis=kpis,
                    explanation=f"📊 Live KPI Computation\nOEE: **{kpis.oee}%**\n"
                               f"Availability: {kpis.availability}% | Performance: {kpis.performance}% | Quality: {kpis.quality}%",
                    reasoning_trace=["Computed fresh KPIs from live sensor data"],
                )
            return TwinResult(
                twin_id=twin_id or "unknown",
                twin_level=TwinLevel.ASSET,
                explanation=f"❌ Twin '{twin_id}' not found for KPI query.",
                reasoning_trace=["KPI lookup failed: twin not found"],
            )
        
        # Refresh KPIs with new sensor data if available
        if data_response and data_response.sensor_data:
            twin.kpis = self.compute_kpis(
                data_response.sensor_data, twin.asset_type, twin.energy_kwh
            )
        
        return TwinResult(
            twin_id=twin.twin_id,
            twin_level=twin.twin_level,
            kpis=twin.kpis,
            alerts=twin.alerts,
            aas_reference=twin.aas_reference,
            explanation=f"📊 KPIs for **{twin.twin_id}**\n\n"
                       f"| Metric | Value |\n|--------|-------|\n"
                       f"| **OEE** | **{twin.kpis.oee}%** |\n"
                       f"| Availability | {twin.kpis.availability}% |\n"
                       f"| Performance | {twin.kpis.performance}% |\n"
                       f"| Quality | {twin.kpis.quality}% |\n"
                       f"| Energy | {twin.kpis.energy_consumption_kwh} kWh |\n"
                       f"| Cycle Time | {twin.kpis.cycle_time_seconds}s |\n\n"
                       f"{'🟢 World-class' if twin.kpis.oee >= 85 else '🟡 Typical' if twin.kpis.oee >= 65 else '🔴 Needs improvement'}",
            reasoning_trace=[f"Retrieved KPIs for {twin.twin_id}"],
        )
    
    def process_list_twins(self, intent_result: IntentResult) -> TwinResult:
        """Process LIST_TWINS intent."""
        if not self._twin_store:
            return TwinResult(
                twin_id="none",
                twin_level=TwinLevel.ASSET,
                explanation="📋 No digital twins created yet. Try: *'Create a digital twin for a CNC machine'*",
                reasoning_trace=["Twin store is empty"],
            )
        
        lines = ["📋 **Active Digital Twins**\n"]
        lines.append("| Twin ID | Type | Level | Floor | OEE | Alerts |")
        lines.append("|---------|------|-------|-------|-----|--------|")
        
        for tid, twin in self._twin_store.items():
            alert_count = len(twin.alerts)
            alert_indicator = f"🔴 {alert_count}" if alert_count > 0 else "🟢 0"
            oee_str = f"{twin.kpis.oee}%"
            lines.append(f"| {tid} | {twin.asset_type} | {twin.twin_level.value} | {twin.floor or 'N/A'} | {oee_str} | {alert_indicator} |")
        
        lines.append(f"\nTotal twins: **{len(self._twin_store)}**")
        
        return TwinResult(
            twin_id="list",
            twin_level=TwinLevel.SYSTEM,
            explanation="\n".join(lines),
            reasoning_trace=[f"Listed {len(self._twin_store)} twins"],
        )
    
    def process_get_alerts(self, intent_result: IntentResult) -> TwinResult:
        """Process GET_ALERTS intent."""
        all_alerts = []
        for tid, twin in self._twin_store.items():
            for alert in twin.alerts:
                alert.asset_id = tid
                all_alerts.append(alert)
        
        if not all_alerts:
            return TwinResult(
                twin_id="alerts",
                twin_level=TwinLevel.SYSTEM,
                explanation="🟢 **No active alerts.** All systems operating within normal parameters.",
                reasoning_trace=["No alerts found across all twins"],
            )
        
        lines = ["🚨 **Active Alerts**\n"]
        for alert in all_alerts:
            icon = "🔴" if alert.severity == AlertSeverity.CRITICAL else "🟡" if alert.severity == AlertSeverity.WARNING else "ℹ️"
            lines.append(f"{icon} **[{alert.severity.value}]** {alert.asset_id}: {alert.message}")
        
        lines.append(f"\nTotal: **{len(all_alerts)}** active alert(s)")
        
        return TwinResult(
            twin_id="alerts",
            twin_level=TwinLevel.SYSTEM,
            alerts=all_alerts,
            explanation="\n".join(lines),
            reasoning_trace=[f"Found {len(all_alerts)} active alerts"],
        )
    
    def process_intent(
        self,
        intent_result: IntentResult,
        data_response: DataResponse = None,
    ) -> TwinResult:
        """Main intent router — process any intent."""
        start = time.time()
        
        try:
            if intent_result.intent == Intent.CREATE_TWIN:
                result = self.process_create_twin(intent_result, data_response)
            elif intent_result.intent == Intent.QUERY_TWIN:
                result = self.process_query_twin(intent_result, data_response)
            elif intent_result.intent == Intent.GET_KPI:
                result = self.process_get_kpi(intent_result, data_response)
            elif intent_result.intent == Intent.LIST_TWINS:
                result = self.process_list_twins(intent_result)
            elif intent_result.intent == Intent.GET_ALERTS:
                result = self.process_get_alerts(intent_result)
            elif intent_result.intent == Intent.GENERAL_QUERY:
                # Use RAG for general queries
                rag_context = self._rag.get_grounding_context(intent_result.raw_message)
                result = TwinResult(
                    twin_id="query",
                    twin_level=TwinLevel.SYSTEM,
                    explanation=f"📖 **Knowledge Base Response**\n\n{rag_context}",
                    reasoning_trace=["Answered from RAG knowledge base"],
                )
            else:
                result = TwinResult(
                    twin_id="unknown",
                    twin_level=TwinLevel.ASSET,
                    explanation="❓ I didn't understand that request. Try:\n"
                               "- *'Create a digital twin for a CNC machine'*\n"
                               "- *'Show me the KPIs'*\n"
                               "- *'List all twins'*\n"
                               "- *'Are there any alerts?'*",
                    reasoning_trace=["Intent not recognized"],
                )
            
            log_agent_action(
                agent_id=AGENT_ID,
                action=f"process_{intent_result.intent.value}",
                tool_used="intent_router",
                duration_ms=(time.time() - start) * 1000,
                reasoning_trace=f"Processed {intent_result.intent.value} → {result.twin_id}"
            )
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"Error processing intent: {e}\n{traceback.format_exc()}")
            log_agent_action(
                agent_id=AGENT_ID,
                action=f"process_{intent_result.intent.value}",
                tool_used="intent_router",
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )
            return TwinResult(
                twin_id="error",
                twin_level=TwinLevel.ASSET,
                explanation=f"⚠️ An error occurred while processing your request: {str(e)}",
                reasoning_trace=[f"Error: {str(e)}"],
            )
    
    def get_all_twins(self) -> dict[str, TwinEntry]:
        return self._twin_store
    
    def get_twin(self, twin_id: str):
        return self._twin_store.get(twin_id)

    # ═══════════════════════════════════════════════════════
    # TOOL: TFT Prediction (NVIDIA Temporal Fusion Transformer)
    # ═══════════════════════════════════════════════════════
    
    def tft_predict(self, twin_id: str, target_sensor: str = "temperature") -> dict:
        """
        Generate multi-horizon quantile prediction using TFT engine.
        Returns p10/p50/p90 forecasts, anomaly risk, and feature importance.
        Integrated with SMIA orchestration and BaSyx AAS.
        """
        start = time.time()
        result = self._tft.predict(twin_id, target_sensor)
        
        log_agent_action(
            agent_id=AGENT_ID, action="tft_predict", tool_used="tft_engine",
            input_data=f"{twin_id}/{target_sensor}",
            duration_ms=(time.time() - start) * 1000,
            reasoning_trace=(
                f"TFT prediction: {result.get('horizon_hours', 0)}h horizon, "
                f"risk={result.get('anomaly_risk', 0)}, "
                f"trend={result.get('trend_direction', 'unknown')}"
            ),
        )
        return result
    
    def tft_record_sensors(self, twin_id: str, sensor_data: dict):
        """Record sensor data for TFT time-series history."""
        self._tft.record_sensors(twin_id, sensor_data)
    
    def get_tft_prediction_submodel(self, twin_id: str) -> dict:
        """Get BaSyx AAS Prediction submodel for a twin."""
        return self._tft.get_prediction_submodel(twin_id)
    
    def get_all_predictions(self, target_sensor: str = "temperature") -> list[dict]:
        """Get TFT predictions for all twins (for dashboard)."""
        return self._tft.predict_all_twins(target_sensor)
    
    # ═══════════════════════════════════════════════════════
    # DASHBOARD AGGREGATION — dynamic data for all views
    # ═══════════════════════════════════════════════════════

    def get_all_alerts(self) -> list[dict]:
        """Aggregate alerts across every twin."""
        out = []
        for tid, twin in self._twin_store.items():
            for alert in twin.alerts:
                out.append({
                    "alert_id": alert.alert_id,
                    "twin_id": tid,
                    "asset_type": twin.asset_type,
                    "severity": alert.severity.value,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "resolved": alert.resolved,
                })
        return out

    def get_twins_by_floor(self) -> dict[str, list[str]]:
        """Group twin IDs by floor."""
        floors: dict[str, list[str]] = {}
        for tid, twin in self._twin_store.items():
            fl = twin.floor or "Unassigned"
            floors.setdefault(fl, []).append(tid)
        return floors

    def get_twins_by_line(self) -> dict[str, list[str]]:
        """Group twin IDs by production line."""
        lines: dict[str, list[str]] = {}
        for tid, twin in self._twin_store.items():
            ln = twin.line or "Unassigned"
            lines.setdefault(ln, []).append(tid)
        return lines

    def get_aggregate_kpis(self) -> dict:
        """Compute global KPIs from all twins."""
        if not self._twin_store:
            return {
                "total_twins": 0, "total_energy_kwh": 0,
                "avg_oee": 0, "avg_availability": 0,
                "avg_performance": 0, "avg_quality": 0,
                "total_alerts": 0, "total_components": 0,
                "floors": 0, "lines": 0,
            }
        twins = list(self._twin_store.values())
        n = len(twins)
        return {
            "total_twins": n,
            "total_energy_kwh": round(sum(t.energy_kwh for t in twins), 1),
            "avg_oee": round(sum(t.kpis.oee for t in twins) / n, 1),
            "avg_availability": round(sum(t.kpis.availability for t in twins) / n, 1),
            "avg_performance": round(sum(t.kpis.performance for t in twins) / n, 1),
            "avg_quality": round(sum(t.kpis.quality for t in twins) / n, 1),
            "total_alerts": sum(len(t.alerts) for t in twins),
            "total_components": sum(len(t.components) for t in twins),
            "floors": len(set(t.floor for t in twins if t.floor)),
            "lines": len(set(t.line for t in twins if t.line)),
        }
