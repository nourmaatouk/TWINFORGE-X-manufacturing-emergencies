"""
TWINFORGE — AAS (Asset Administration Shell) Manager.
Creates and manages digital twin AAS structures using
BaSyx-compatible patterns (in-memory model objects).
Follows IDTA standard submodel templates.
"""
from __future__ import annotations
import uuid
import json
from datetime import datetime
from typing import Any
from twinforge.core.schemas import TwinLevel


# ════════════════════════════════════════════════════════════
# AAS In-Memory Models (BaSyx-compatible patterns)
# ════════════════════════════════════════════════════════════

class Property:
    """A single property in a Submodel element collection."""
    def __init__(self, id_short: str, value: Any, value_type: str = "string", unit: str = ""):
        self.id_short = id_short
        self.value = value
        self.value_type = value_type
        self.unit = unit
    
    def to_dict(self) -> dict:
        return {
            "idShort": self.id_short,
            "modelType": "Property",
            "value": str(self.value),
            "valueType": self.value_type,
            "unit": self.unit,
        }


class SubmodelElementCollection:
    """A collection of properties / elements."""
    def __init__(self, id_short: str):
        self.id_short = id_short
        self.elements: list[Property] = []
    
    def add_property(self, id_short: str, value: Any, value_type: str = "string", unit: str = "") -> Property:
        prop = Property(id_short, value, value_type, unit)
        self.elements.append(prop)
        return prop
    
    def to_dict(self) -> dict:
        return {
            "idShort": self.id_short,
            "modelType": "SubmodelElementCollection",
            "value": [e.to_dict() for e in self.elements],
        }


class Submodel:
    """An AAS Submodel (e.g., Nameplate, TechnicalData, OperationalData)."""
    def __init__(self, id_short: str, semantic_id: str = ""):
        self.id = f"urn:twinforge:submodel:{id_short}:{uuid.uuid4().hex[:8]}"
        self.id_short = id_short
        self.semantic_id = semantic_id
        self.elements: list[Property | SubmodelElementCollection] = []
    
    def add_property(self, id_short: str, value: Any, value_type: str = "string", unit: str = "") -> Property:
        prop = Property(id_short, value, value_type, unit)
        self.elements.append(prop)
        return prop
    
    def add_collection(self, id_short: str) -> SubmodelElementCollection:
        coll = SubmodelElementCollection(id_short)
        self.elements.append(coll)
        return coll
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "idShort": self.id_short,
            "modelType": "Submodel",
            "semanticId": self.semantic_id,
            "submodelElements": [e.to_dict() for e in self.elements],
        }


class AssetAdministrationShell:
    """An Asset Administration Shell (AAS)."""
    def __init__(self, id_short: str, asset_type: str = "Instance"):
        self.id = f"urn:twinforge:aas:{id_short}:{uuid.uuid4().hex[:8]}"
        self.id_short = id_short
        self.asset_type = asset_type
        self.asset_id = f"urn:twinforge:asset:{id_short}:{uuid.uuid4().hex[:8]}"
        self.submodels: list[Submodel] = []
        self.created_at = datetime.utcnow()
    
    def add_submodel(self, submodel: Submodel) -> Submodel:
        self.submodels.append(submodel)
        return submodel
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "idShort": self.id_short,
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": self.asset_type,
                "globalAssetId": self.asset_id,
            },
            "submodels": [sm.to_dict() for sm in self.submodels],
            "createdAt": self.created_at.isoformat(),
        }


# ════════════════════════════════════════════════════════════
# AAS MANAGER
# ════════════════════════════════════════════════════════════

class AASManager:
    """
    Creates and manages AAS structures for digital twins.
    Supports Component, Asset, System, and Process twin levels.
    """
    
    def __init__(self):
        self._shells: dict[str, AssetAdministrationShell] = {}
    
    def create_twin_aas(
        self,
        twin_id: str,
        twin_level: TwinLevel,
        asset_type: str = "CNC",
        name: str = "",
        floor: str = "",
        line: str = "",
        energy_kwh: float = 0.0,
        components: list[dict] = None,
        sensor_data: dict = None,
        **kwargs,
    ) -> AssetAdministrationShell:
        """Create a full AAS for a digital twin."""
        
        aas = AssetAdministrationShell(twin_id, "Instance")
        
        # ── Nameplate Submodel (IDTA 02006-2-0) ──────────
        nameplate = Submodel("Nameplate", "urn:IDTA:Nameplate:2.0")
        nameplate.add_property("ManufacturerName", f"TwinForge AutoGen")
        nameplate.add_property("ManufacturerProductDesignation", f"{asset_type} {twin_id}")
        nameplate.add_property("SerialNumber", f"TF-{twin_id}")
        nameplate.add_property("YearOfConstruction", str(datetime.utcnow().year))
        nameplate.add_property("PhysicalAddress_Floor", floor or "N/A")
        nameplate.add_property("PhysicalAddress_Line", line or "N/A")
        aas.add_submodel(nameplate)
        
        # ── Technical Data Submodel (IDTA 02003-1-2) ─────
        tech_data = Submodel("TechnicalData", "urn:IDTA:TechnicalData:1.2")
        tech_data.add_property("AssetType", asset_type)
        tech_data.add_property("TwinLevel", twin_level.value)
        tech_data.add_property("RatedPower", str(energy_kwh), "double", "kWh")
        tech_data.add_property("ProductionFloor", floor)
        tech_data.add_property("ProductionLine", line)
        
        # Add component info
        if components:
            comp_coll = tech_data.add_collection("Components")
            for i, comp in enumerate(components):
                comp_name = comp.get("name", f"component_{i+1}")
                comp_type = comp.get("type", "unknown")
                comp_coll.add_property(f"Component_{i+1}_Name", comp_name)
                comp_coll.add_property(f"Component_{i+1}_Type", comp_type)
        
        aas.add_submodel(tech_data)
        
        # ── Operational Data Submodel ─────────────────────
        op_data = Submodel("OperationalData", "urn:twinforge:OperationalData:1.0")
        if sensor_data:
            for sensor_type, sensor_info in sensor_data.items():
                op_data.add_property(
                    sensor_type,
                    str(sensor_info.get("value", 0)),
                    "double",
                    sensor_info.get("unit", "")
                )
        op_data.add_property("EnergyConsumption", str(energy_kwh), "double", "kWh")
        op_data.add_property("OperationalStatus", "Active")
        op_data.add_property("LastUpdate", datetime.utcnow().isoformat())
        aas.add_submodel(op_data)
        
        # ── Component Submodels (for Asset-level twins) ───
        if components and twin_level in (TwinLevel.ASSET, TwinLevel.SYSTEM):
            for i, comp in enumerate(components):
                comp_sm = Submodel(f"Component_{comp.get('name', i+1)}", "urn:twinforge:Component:1.0")
                comp_sm.add_property("ComponentName", comp.get("name", f"component_{i+1}"))
                comp_sm.add_property("ComponentType", comp.get("type", "generic"))
                comp_sm.add_property("Status", comp.get("status", "operational"))
                comp_sm.add_property("HealthScore", str(comp.get("health", 95)), "double", "%")
                aas.add_submodel(comp_sm)
        
        # Store
        self._shells[twin_id] = aas
        return aas
    
    def get_aas(self, twin_id: str) -> AssetAdministrationShell | None:
        return self._shells.get(twin_id)
    
    def list_aas(self) -> list[str]:
        return list(self._shells.keys())
    
    def delete_aas(self, twin_id: str) -> bool:
        if twin_id in self._shells:
            del self._shells[twin_id]
            return True
        return False
    
    def validate_submodel(self, submodel: Submodel) -> tuple[bool, list[str]]:
        """Validate submodel structure against IDTA patterns."""
        errors = []
        if not submodel.id_short:
            errors.append("Submodel missing idShort")
        if not submodel.elements:
            errors.append(f"Submodel '{submodel.id_short}' has no elements")
        for elem in submodel.elements:
            if not elem.id_short:
                errors.append("Element missing idShort")
        return len(errors) == 0, errors
