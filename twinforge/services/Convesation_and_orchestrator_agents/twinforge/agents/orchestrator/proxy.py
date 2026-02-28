"""
TWINFORGE — Remote Orchestrator Proxy.
Implements the same interface as TwinOrchestratorAgent but calls the Port 8002 microservice.
Used by the Dashboard and Agent 1 to maintain compatibility with existing code.
"""
from __future__ import annotations
import requests
import logging
from typing import Any, Optional, Dict, List
from twinforge.core.schemas import IntentResult, DataResponse, TwinResult, TwinEntry, Intent

logger = logging.getLogger("twinforge.proxy.orchestrator")

class RemoteOrchestratorProxy:
    """Proxy for Agent 2 running on Port 8002."""
    
    def __init__(self, base_url: str = "http://localhost:8002"):
        self.base_url = base_url
        self._overview_cache = None
        self._overview_ts = 0

    def process_intent(self, intent_result: IntentResult, data_response: Optional[DataResponse] = None) -> TwinResult:
        resp = requests.post(
            f"{self.base_url}/process_intent",
            json={
                "intent_result": intent_result.model_dump(mode="json"),
                "data_response": data_response.model_dump(mode="json") if data_response else None
            },
            timeout=30
        )
        resp.raise_for_status()
        return TwinResult(**resp.json())

    def get_all_twins(self) -> Dict[str, TwinEntry]:
        resp = requests.get(f"{self.base_url}/twins", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return {t["twin_id"]: TwinEntry(**t) for t in data}

    def get_twin(self, twin_id: str) -> Optional[TwinEntry]:
        resp = requests.get(f"{self.base_url}/twins/{twin_id}", timeout=5)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return TwinEntry(**resp.json())

    # ─── Cached Overview (single HTTP call instead of 4) ────
    def _fetch_overview(self) -> Dict[str, Any]:
        import time
        now = time.time()
        if self._overview_cache is None or (now - self._overview_ts) > 2:
            try:
                resp = requests.get(f"{self.base_url}/dashboard/overview", timeout=5)
                if resp.status_code == 200:
                    self._overview_cache = resp.json()
                else:
                    self._overview_cache = {}
            except Exception:
                self._overview_cache = {}
            self._overview_ts = now
        return self._overview_cache

    def get_aggregate_kpis(self) -> Dict[str, Any]:
        return self._fetch_overview().get("aggregate_kpis", {})

    def get_all_alerts(self) -> List[Any]:
        return self._fetch_overview().get("alerts", [])

    def get_twins_by_floor(self) -> Dict[str, List[str]]:
        twins = self.get_all_twins()
        floors: Dict[str, List[str]] = {}
        for twin_id, twin in twins.items():
            floor = twin.floor or "Unassigned"
            floors.setdefault(floor, []).append(twin_id)
        return floors

    def get_twins_by_line(self) -> Dict[str, List[str]]:
        twins = self.get_all_twins()
        lines: Dict[str, List[str]] = {}
        for twin_id, twin in twins.items():
            line = twin.line or "Unassigned"
            lines.setdefault(line, []).append(twin_id)
        return lines
        
    def get_all_predictions(self, target_sensor: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/dashboard/predictions", params={"sensor": target_sensor}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("predictions", {})
        return {}
        
    def tft_predict(self, twin_id: str, sensor: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/dashboard/predictions/{twin_id}", params={"sensor": sensor}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("prediction", {})
        return {}
        
    def get_tft_prediction_submodel(self, twin_id: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/dashboard/predictions/{twin_id}", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("aas_prediction_submodel", {})
        return {}
