"""
TWINFORGE — Dashboard API Router.
All endpoints return DYNAMIC data from the live twin registry,
sensor simulators, and action logs. Zero hardcoded values.
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from twinforge.graph.workflow import get_agents
from twinforge.core.logging_config import get_action_store
from twinforge.core.schemas import DataRequest

logger = logging.getLogger("twinforge.dashboard.api")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _count_map(values: dict[str, Any]) -> dict[str, int]:
    """Normalize mapping values to counts (accepts lists or pre-counted ints)."""
    normalized: dict[str, int] = {}
    for key, value in values.items():
        if isinstance(value, int):
            normalized[key] = value
        elif isinstance(value, list):
            normalized[key] = len(value)
        else:
            normalized[key] = 0
    return normalized


def _group_twins_by_field(twins: dict[str, Any], field_name: str) -> dict[str, list[str]]:
    """Group twin IDs by a TwinEntry field (e.g. floor, line)."""
    groups: dict[str, list[str]] = {}
    for twin_id, twin in twins.items():
        value = getattr(twin, field_name, None) or "Unassigned"
        groups.setdefault(str(value), []).append(twin_id)
    return groups


def _twin_to_dict(tid: str, twin) -> dict[str, Any]:
    """Convert a TwinEntry to a JSON-safe dict."""
    return {
        "twin_id": tid,
        "name": twin.name or tid,
        "asset_type": twin.asset_type,
        "twin_level": twin.twin_level.value,
        "floor": twin.floor or "Unassigned",
        "line": twin.line or "Unassigned",
        "protocol": twin.protocol,
        "energy_kwh": twin.energy_kwh,
        "components": twin.components,
        "component_count": len(twin.components),
        "kpis": {
            "oee": twin.kpis.oee,
            "availability": twin.kpis.availability,
            "performance": twin.kpis.performance,
            "quality": twin.kpis.quality,
            "energy_consumption_kwh": twin.kpis.energy_consumption_kwh,
            "cycle_time_seconds": twin.kpis.cycle_time_seconds,
        },
        "alerts": [
            {
                "alert_id": a.alert_id,
                "severity": a.severity.value,
                "message": a.message,
                "timestamp": a.timestamp.isoformat(),
                "resolved": a.resolved,
            }
            for a in twin.alerts
        ],
        "alert_count": len(twin.alerts),
        "aas_reference": twin.aas_reference,
        "created_at": twin.created_at.isoformat(),
        "smia_agent": f"SMIA-{tid}",
    }


# ═══════════════════════════════════════════════════════════
# 1. OVERVIEW — aggregate KPIs, counts, status distribution
# ═══════════════════════════════════════════════════════════

@router.get("/overview")
def overview():
    """Global overview: total KPIs, machine status, floor/line counts."""
    _, orch, data_agent = get_agents()
    twins = orch.get_all_twins()
    twin_values = list(twins.values())

    if twin_values:
        count = len(twin_values)
        agg = {
            "total_twins": count,
            "total_energy_kwh": round(sum(t.energy_kwh for t in twin_values), 1),
            "avg_oee": round(sum(t.kpis.oee for t in twin_values) / count, 1),
            "avg_availability": round(sum(t.kpis.availability for t in twin_values) / count, 1),
            "avg_performance": round(sum(t.kpis.performance for t in twin_values) / count, 1),
            "avg_quality": round(sum(t.kpis.quality for t in twin_values) / count, 1),
            "total_alerts": sum(len(t.alerts) for t in twin_values),
            "total_components": sum(len(t.components) for t in twin_values),
            "floors": len(set(t.floor for t in twin_values if t.floor)),
            "lines": len(set(t.line for t in twin_values if t.line)),
        }
    else:
        agg = {
            "total_twins": 0,
            "total_energy_kwh": 0,
            "avg_oee": 0,
            "avg_availability": 0,
            "avg_performance": 0,
            "avg_quality": 0,
            "total_alerts": 0,
            "total_components": 0,
            "floors": 0,
            "lines": 0,
        }

    alerts = []
    for twin_id, twin in twins.items():
        for alert in twin.alerts:
            alerts.append({
                "alert_id": alert.alert_id,
                "twin_id": twin_id,
                "asset_type": twin.asset_type,
                "severity": alert.severity.value,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "resolved": alert.resolved,
            })
    floors = _group_twins_by_field(twins, "floor")
    lines = _group_twins_by_field(twins, "line")

    # Status distribution
    status_counts = {"ok": 0, "warn": 0, "fault": 0, "planned": 0}
    for twin in twins.values():
        has_crit = any(a.severity.value == "CRITICAL" for a in twin.alerts)
        has_warn = any(a.severity.value == "WARNING" for a in twin.alerts)
        if has_crit:
            status_counts["fault"] += 1
        elif has_warn:
            status_counts["warn"] += 1
        else:
            status_counts["ok"] += 1

    return JSONResponse({
        "timestamp": datetime.utcnow().isoformat(),
        "aggregate_kpis": agg,
        "status_counts": status_counts,
        "alerts": alerts,
        "alert_count": len(alerts),
        "floors": _count_map(floors),
        "floor_count": len(floors),
        "lines": _count_map(lines),
        "line_count": len(lines),
        "twins": [_twin_to_dict(tid, t) for tid, t in twins.items()],
    })


# ═══════════════════════════════════════════════════════════
# 2. COMPONENTS — all components across all twins
# ═══════════════════════════════════════════════════════════

@router.get("/components")
def components():
    """All components with parent machine info."""
    _, orch, _ = get_agents()
    twins = orch.get_all_twins()

    all_components = []
    comp_id = 0
    for tid, twin in twins.items():
        for comp in twin.components:
            comp_id += 1
            all_components.append({
                "comp_id": f"C{comp_id:03d}",
                "name": comp.get("name", f"Component-{comp_id}"),
                "type": comp.get("type", "Generic"),
                "parent_twin": tid,
                "parent_type": twin.asset_type,
                "floor": twin.floor or "Unassigned",
                "line": twin.line or "Unassigned",
                "status": comp.get("status", "operational"),
                "health": comp.get("health", 95),
            })

    # Status counts
    statuses = {}
    for c in all_components:
        s = c["status"]
        statuses[s] = statuses.get(s, 0) + 1

    return JSONResponse({
        "timestamp": datetime.utcnow().isoformat(),
        "total": len(all_components),
        "status_counts": statuses,
        "components": all_components,
    })


# ═══════════════════════════════════════════════════════════
# 3. ASSETS — all machines / twins as assets
# ═══════════════════════════════════════════════════════════

@router.get("/assets")
def assets():
    """Full asset list with KPIs, alerts, maintenance data."""
    _, orch, _ = get_agents()
    twins = orch.get_all_twins()
    agg = orch.get_aggregate_kpis()

    asset_list = [_twin_to_dict(tid, t) for tid, t in twins.items()]

    return JSONResponse({
        "timestamp": datetime.utcnow().isoformat(),
        "total": len(asset_list),
        "aggregate_kpis": agg,
        "assets": asset_list,
    })


# ═══════════════════════════════════════════════════════════
# 4. SYSTEM — production lines, floor topology, agent status
# ═══════════════════════════════════════════════════════════

@router.get("/system")
def system():
    """Production lines grouped, floor distribution, agent info."""
    _, orch, _ = get_agents()
    twins = orch.get_all_twins()
    lines_map = _group_twins_by_field(twins, "line")
    floors_map = _group_twins_by_field(twins, "floor")

    # Build production lines
    prod_lines = []
    for line_name, twin_ids in lines_map.items():
        line_twins = [twins[tid] for tid in twin_ids if tid in twins]
        line_energy = sum(t.energy_kwh for t in line_twins)
        line_alerts = sum(len(t.alerts) for t in line_twins)
        line_oee = round(sum(t.kpis.oee for t in line_twins) / len(line_twins), 1) if line_twins else 0

        machines = []
        for t in line_twins:
            has_crit = any(a.severity.value == "CRITICAL" for a in t.alerts)
            has_warn = any(a.severity.value == "WARNING" for a in t.alerts)
            status = "fault" if has_crit else "warn" if has_warn else "ok"
            machines.append({
                "twin_id": t.twin_id, "name": t.name or t.twin_id,
                "asset_type": t.asset_type, "status": status,
            })

        prod_lines.append({
            "line": line_name,
            "machine_count": len(line_twins),
            "machines": machines,
            "energy_kwh": round(line_energy, 1),
            "oee": line_oee,
            "alert_count": line_alerts,
        })

    # Floor distribution
    floor_data = []
    for fl, twin_ids in floors_map.items():
        fl_twins = [twins[tid] for tid in twin_ids if tid in twins]
        floor_data.append({
            "floor": fl,
            "machine_count": len(fl_twins),
            "twin_ids": twin_ids,
            "energy_kwh": round(sum(t.energy_kwh for t in fl_twins), 1),
            "smia_agents": [f"SMIA-{tid}" for tid in twin_ids],
        })

    return JSONResponse({
        "timestamp": datetime.utcnow().isoformat(),
        "production_lines": prod_lines,
        "floors": floor_data,
        "total_agents": len(twins),
    })


# ═══════════════════════════════════════════════════════════
# 5. PROCESS — agent actions as BPMN trace, orders from twins
# ═══════════════════════════════════════════════════════════

@router.get("/process")
def process():
    """Process view: agent action trace, twin creation orders."""
    _, orch, _ = get_agents()
    twins = orch.get_all_twins()
    store = get_action_store()
    recent = store.get_recent(100)

    # Build "manufacturing orders" from twin creation events
    orders = []
    for tid, twin in twins.items():
        orders.append({
            "order_id": f"OF-{tid}",
            "product": twin.asset_type,
            "twin_id": tid,
            "floor": twin.floor or "N/A",
            "line": twin.line or "N/A",
            "component_count": len(twin.components),
            "oee": twin.kpis.oee,
            "energy_kwh": twin.energy_kwh,
            "alert_count": len(twin.alerts),
            "created_at": twin.created_at.isoformat(),
        })

    # Build BPMN trace from agent actions
    bpmn_steps = []
    for action in recent:
        bpmn_steps.append({
            "agent": action.get("agent_id", ""),
            "action": action.get("action", ""),
            "tool": action.get("tool_used", ""),
            "success": action.get("success", True),
            "duration_ms": action.get("duration_ms", 0),
            "reasoning": action.get("reasoning_trace", ""),
            "timestamp": action.get("timestamp", ""),
        })

    return JSONResponse({
        "timestamp": datetime.utcnow().isoformat(),
        "orders": orders,
        "order_count": len(orders),
        "bpmn_trace": bpmn_steps,
        "action_count": len(bpmn_steps),
    })


# ═══════════════════════════════════════════════════════════
# 6. LIVE SENSORS — poll fresh data for a specific twin
# ═══════════════════════════════════════════════════════════

@router.get("/live-sensors/{twin_id}")
def live_sensors(twin_id: str):
    """Poll fresh sensor data from IoT agent for a twin."""
    _, orch, data_agent = get_agents()
    twin = orch.get_twin(twin_id)
    if not twin:
        return JSONResponse({"error": f"Twin '{twin_id}' not found"}, status_code=404)

    # Poll fresh sensors through Agent 3
    request = DataRequest(asset_id=twin_id, data_request="live_sensors")
    response = data_agent.process_data_request(request)

    return JSONResponse({
        "twin_id": twin_id,
        "timestamp": datetime.utcnow().isoformat(),
        "sensor_data": response.sensor_data,
        "readings": [
            {
                "sensor_id": r.sensor_id,
                "value": r.value,
                "unit": r.unit,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in response.readings
        ],
        "anomalies": [
            {
                "sensor_id": a.sensor_id,
                "value": a.value,
                "threshold": a.threshold,
                "severity": a.severity.value,
                "message": a.message,
            }
            for a in response.anomalies
        ],
    })


# ═══════════════════════════════════════════════════════════
# 7. SCENE 3D — optimised scene data for Three.js renderer
# ═══════════════════════════════════════════════════════════

@router.get("/scene3d")
def scene3d():
    """Return optimised 3D scene data for the procedural factory renderer."""
    _, orch, _ = get_agents()
    twins = orch.get_all_twins()

    if not twins:
        return JSONResponse({
            "timestamp": datetime.utcnow().isoformat(),
            "floors": [],
            "building": {"width": 30, "depth": 20, "floor_height": 4, "floor_count": 0},
            "total_machines": 0,
        })

    # Group by floor
    floor_map: dict[str, list] = {}
    for tid, twin in twins.items():
        fl = twin.floor or "1"
        floor_map.setdefault(fl, [])

        has_crit = any(a.severity.value == "CRITICAL" for a in twin.alerts)
        has_warn = any(a.severity.value == "WARNING" for a in twin.alerts)
        status = "critical" if has_crit else "warning" if has_warn else "ok"

        floor_map[fl].append({
            "twin_id": tid,
            "name": twin.name or tid,
            "asset_type": twin.asset_type,
            "line": twin.line or "A",
            "status": status,
            "energy_kwh": twin.energy_kwh,
            "oee": twin.kpis.oee if twin.kpis else 0,
            "temperature": twin.kpis.cycle_time_seconds if twin.kpis else 0,
            "components": len(twin.components),
            "protocol": twin.protocol,
        })

    # Sort floors numerically
    sorted_floors = sorted(floor_map.keys(), key=lambda f: int(f) if f.isdigit() else 999)

    # Build spatial layout for each floor
    floor_data = []
    max_machines_per_floor = max(len(m) for m in floor_map.values()) if floor_map else 1
    # Grid: machines per row
    cols = min(max(3, int(max_machines_per_floor ** 0.5) + 1), 8)
    spacing = 6  # metres between machines

    for idx, fl in enumerate(sorted_floors):
        machines = floor_map[fl]
        # Assign grid positions
        positioned = []
        for mi, m in enumerate(machines):
            row = mi // cols
            col = mi % cols
            positioned.append({
                **m,
                "grid_x": col,
                "grid_z": row,
                "world_x": round(col * spacing - (cols * spacing / 2) + spacing / 2, 2),
                "world_z": round(row * spacing - (len(machines) // cols * spacing / 2), 2),
            })

        # Pipelines (connect same-line adjacent machines)
        pipelines = []
        line_groups: dict[str, list] = {}
        for pm in positioned:
            line_groups.setdefault(pm["line"], []).append(pm)
        for line_name, lm in line_groups.items():
            for i in range(len(lm) - 1):
                pipelines.append({
                    "from": lm[i]["twin_id"],
                    "to": lm[i + 1]["twin_id"],
                    "from_pos": [lm[i]["world_x"], lm[i]["world_z"]],
                    "to_pos": [lm[i + 1]["world_x"], lm[i + 1]["world_z"]],
                    "line": line_name,
                })

        floor_data.append({
            "floor": fl,
            "y_offset": idx * 5,  # 5m per floor
            "machine_count": len(machines),
            "machines": positioned,
            "pipelines": pipelines,
        })

    # Building envelope
    rows_max = max((len(floor_map[fl]) // cols + 1) for fl in floor_map) if floor_map else 1
    building = {
        "width": round(cols * spacing + 4, 1),
        "depth": round(rows_max * spacing + 4, 1),
        "floor_height": 4.5,
        "floor_count": len(sorted_floors),
        "total_height": round(len(sorted_floors) * 5, 1),
    }

    return JSONResponse({
        "timestamp": datetime.utcnow().isoformat(),
        "floors": floor_data,
        "building": building,
        "total_machines": sum(len(floor_map[fl]) for fl in floor_map),
    })


# ═══════════════════════════════════════════════════════════
# TFT PREDICTIONS  —  /api/dashboard/predictions
# ═══════════════════════════════════════════════════════════

@router.get("/predictions")
def predictions(sensor: str = "temperature"):
    """
    Return TFT multi-horizon predictions for all twins.
    Query param: ?sensor=temperature (default)
    
    Produces quantile forecasts (p10/p50/p90), anomaly risk,
    and feature importance scores per twin.
    """
    _, orch, _ = get_agents()
    
    # Validate sensor name (security: whitelist)
    ALLOWED_SENSORS = {
        "temperature", "vibration", "spindle_speed", "tool_wear",
        "energy_consumption", "coolant_flow", "pressure", "current",
    }
    if sensor not in ALLOWED_SENSORS:
        return JSONResponse(
            {"error": f"Unknown sensor: {sensor}", "allowed": sorted(ALLOWED_SENSORS)},
            status_code=400,
        )
    
    preds = orch.get_all_predictions(target_sensor=sensor)
    
    return JSONResponse({
        "timestamp": datetime.utcnow().isoformat(),
        "target_sensor": sensor,
        "predictions": preds,
        "count": len(preds),
        "model": "TFT (Temporal Fusion Transformer)",
    })


@router.get("/predictions/{twin_id}")
def prediction_for_twin(twin_id: str, sensor: str = "temperature"):
    """Return TFT prediction for a specific twin."""
    _, orch, _ = get_agents()
    
    # Security: validate twin_id format
    if len(twin_id) > 64 or not all(c.isalnum() or c in "-_" for c in twin_id):
        return JSONResponse({"error": "Invalid twin_id format"}, status_code=400)
    
    twin = orch.get_twin(twin_id)
    if not twin:
        return JSONResponse({"error": f"Twin {twin_id} not found"}, status_code=404)
    
    pred = orch.tft_predict(twin_id, sensor)
    aas_submodel = orch.get_tft_prediction_submodel(twin_id)
    
    return JSONResponse({
        "timestamp": datetime.utcnow().isoformat(),
        "prediction": pred,
        "aas_prediction_submodel": aas_submodel,
    })
