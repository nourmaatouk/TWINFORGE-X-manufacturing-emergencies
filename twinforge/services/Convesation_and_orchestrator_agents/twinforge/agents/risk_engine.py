"""
TWINFORGE-X — Agent 6: Risk Intelligence Engine
=================================================
Multi-risk detection fusing IoT telemetry, ML anomaly detection (Isolation Forest),
vibration analysis, thermal modelling, geofencing and predictive threat assessment
into a single Global Risk Score.

AI Methods used:
  - Isolation Forest (unsupervised anomaly detection, sklearn)
  - Z-score statistical deviation
  - Weighted multi-vector risk fusion
  - Time-series trend extrapolation (predictive forecast)

ARSII Challenge: AI-Powered Real-Time Industrial Risk Prevention & Emergency Intelligence
"""
from __future__ import annotations

import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

_UTC = timezone.utc

# ── Optional ML import (graceful fallback if sklearn not installed) ──────────
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# ── Simulated machine bank ──────────────────────────────────────────────────

MACHINES = [
    {"id": "CNC-001",  "zone": "A", "floor": 1, "type": "CNC",      "safe_temp": 75, "safe_vib": 4.0},
    {"id": "ROB-002",  "zone": "A", "floor": 1, "type": "ROBOT",    "safe_temp": 65, "safe_vib": 2.5},
    {"id": "CNV-003",  "zone": "B", "floor": 1, "type": "CONVEYOR", "safe_temp": 55, "safe_vib": 3.0},
    {"id": "PRS-004",  "zone": "B", "floor": 2, "type": "PRESS",    "safe_temp": 80, "safe_vib": 6.0},
    {"id": "WLD-005",  "zone": "C", "floor": 2, "type": "WELDER",   "safe_temp": 90, "safe_vib": 5.5},
    {"id": "DRL-006",  "zone": "C", "floor": 2, "type": "DRILL",    "safe_temp": 70, "safe_vib": 3.5},
]

RESTRICTED_ZONES = {"A", "C"}

# ── ML State: Sliding windows + fitted models per machine ────────────────────

class _MLState:
    """Maintains per-machine sliding windows for Isolation Forest training."""
    MIN_SAMPLES = 25  # need this many readings before ML fires

    def __init__(self):
        self.windows: Dict[str, deque] = {m["id"]: deque(maxlen=80) for m in MACHINES}
        self.fitted: Dict[str, bool] = {m["id"]: False for m in MACHINES}
        self.models: Dict[str, IsolationForest] = {}
        self.scalers: Dict[str, StandardScaler] = {}
        self.anomaly_scores: Dict[str, float] = {m["id"]: 0.0 for m in MACHINES}
        self.z_scores: Dict[str, float] = {m["id"]: 0.0 for m in MACHINES}

    def feed(self, machine_id: str, temp: float, vib: float, energy: float) -> float:
        """Feed new reading; return ML anomaly score 0–100."""
        self.windows[machine_id].append([temp, vib, energy])
        data = list(self.windows[machine_id])

        if len(data) < self.MIN_SAMPLES:
            # Fallback: basic Z-score on temp
            temps = [d[0] for d in data]
            if len(temps) > 2:
                mean = sum(temps) / len(temps)
                std  = (sum((t - mean) ** 2 for t in temps) / len(temps)) ** 0.5
                z = abs(temps[-1] - mean) / max(std, 0.01)
                self.z_scores[machine_id] = round(min(100, z * 20), 1)
                return self.z_scores[machine_id]
            return 0.0

        if not SKLEARN_AVAILABLE:
            return self.z_scores.get(machine_id, 0.0)

        import numpy as np
        X = np.array(data)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = IsolationForest(
            n_estimators=50,
            contamination=0.12,
            random_state=42,
            max_samples="auto",
        )
        model.fit(X_scaled)
        self.models[machine_id] = model
        self.scalers[machine_id] = scaler
        self.fitted[machine_id] = True

        latest = X_scaled[-1:, :]
        decision = model.decision_function(latest)[0]   # negative → anomaly
        # Map decision score to 0–100 (higher = more anomalous)
        anomaly = float(max(0.0, min(100.0, (-decision + 0.2) * 200)))
        self.anomaly_scores[machine_id] = round(anomaly, 1)

        # Z-score on temp stream (complementary)
        temps = X[:, 0]
        z = abs((temps[-1] - temps.mean()) / max(temps.std(), 0.01))
        self.z_scores[machine_id] = round(min(100, z * 25), 1)

        return self.anomaly_scores[machine_id]


_ml = _MLState()


# ── Internal simulation state ─────────────────────────────────────────────────

class _Sim:
    def __init__(self):
        self.t0 = time.time()
        self.machines: Dict[str, dict] = {}
        for m in MACHINES:
            self.machines[m["id"]] = {
                "temp":            m["safe_temp"] * 0.60,
                "vib":             m["safe_vib"]  * 0.50,
                "energy":          random.uniform(20, 80),
                "temp_dir":        1,
                "vib_dir":         1,
                "phase":           random.uniform(0, math.pi * 2),
                "workers_present": False,
            }
        self.active_scenario:  Optional[str] = None
        self.scenario_t:       float = 0.0
        self.scenario_machine: str = ""

    # Agent comm message buffer (last 30)
    agent_messages: deque = deque(maxlen=30)


_sim = _Sim()

# ── SMIA Agent message simulator ─────────────────────────────────────────────

_AGENT_MSG_TEMPLATES = [
    ("Agent-3·IoT",      "Agent-4·Verifier",   "SENSOR_DATA",
        lambda m: f"{m['id']}: temp={m['temp']:.1f}°C vib={m['vib']:.2f}g"),
    ("Agent-4·Verifier", "Agent-5·Security",   "ANOMALY_CHECK",
        lambda m: f"validating telemetry vector for {m['id']}"),
    ("Agent-5·Security", "Agent-6·Risk",        "THREAT_VECTOR",
        lambda m: f"zone={m['zone']} floor={m['floor']} → threat index computed"),
    ("Agent-6·Risk",     "Orchestrator·Ag2",   "RISK_REPORT",
        lambda m: f"fusion score dispatched to orchestrator"),
    ("Agent-4·Verifier", "Agent-6·Risk",        "DEVIATION_ALERT",
        lambda m: f"statistical deviation detected on {m['id']}"),
    ("Orchestrator·Ag2", "Dashboard",            "ACTION_COMMAND",
        lambda m: f"dashboard notified — update risk view"),
]

def _emit_agent_messages(machines_data: list):
    """Generate realistic SMIA inter-agent communication messages."""
    now = datetime.now(_UTC).strftime("%H:%M:%S")
    # Pick 2–3 templates per cycle
    chosen = random.sample(_AGENT_MSG_TEMPLATES, k=min(3, len(_AGENT_MSG_TEMPLATES)))
    mdata = random.choice(machines_data)
    for from_a, to_a, mtype, content_fn in chosen:
        _sim.agent_messages.appendleft({
            "ts":      now,
            "from":    from_a,
            "to":      to_a,
            "type":    mtype,
            "content": content_fn(mdata),
        })


# ── Risk primitives ───────────────────────────────────────────────────────────

@dataclass
class MachineRisk:
    machine_id:       str
    zone:             str
    floor:            int
    machine_type:     str
    temp:             float
    vibration:        float
    energy:           float
    workers_present:  bool
    fire_risk:        float
    intrusion_risk:   float
    failure_risk:     float
    worker_risk:      float
    ml_anomaly_score: float     # Isolation Forest output 0–100
    z_score:          float     # Z-score deviation 0–100
    ai_method:        str       # method used for anomaly detection
    risk_score:       float
    risk_level:       str
    alerts:           List[str] = field(default_factory=list)


@dataclass
class RiskSnapshot:
    timestamp:       str
    global_score:    float
    global_level:    str
    emergency_mode:  bool
    recommendation:  str
    machines:        List[MachineRisk]
    predictions:     List[dict]
    scenario:        Optional[str]
    agent_messages:  List[dict]
    ai_info:         dict        # AI methods metadata


# ── Telemetry simulation ─────────────────────────────────────────────────────

def _tick_machine(mid: str, meta: dict, now: float) -> dict:
    s = _sim.machines[mid]
    elapsed = now - _sim.t0

    # Natural sine-wave drift
    temp_drift = math.sin(elapsed / 60 + s["phase"]) * 8
    vib_drift  = math.sin(elapsed / 45 + s["phase"]) * 0.8
    eng_drift  = math.sin(elapsed / 90 + s["phase"]) * 10

    # Scenario amplifiers
    temp_boost = 0.0
    vib_boost  = 0.0
    if _sim.active_scenario and _sim.scenario_machine == mid:
        age = now - _sim.scenario_t
        if _sim.active_scenario == "overheat":
            temp_boost = min(age * 1.2, 40)
        elif _sim.active_scenario == "cascade":
            temp_boost = min(age * 0.8, 30)
            vib_boost  = min(age * 0.15, 5)

    s["temp"]   = meta["safe_temp"] * 0.60 + temp_drift + temp_boost
    s["vib"]    = meta["safe_vib"]  * 0.50 + vib_drift  + vib_boost
    s["energy"] = max(10, 50 + eng_drift)

    # Worker presence random walk
    if random.random() < 0.04:
        s["workers_present"] = not s["workers_present"]
    if _sim.active_scenario == "intrusion" and _sim.scenario_machine == mid:
        s["workers_present"] = True

    out = dict(s)
    out["id"]    = meta["id"]
    out["zone"]  = meta["zone"]
    out["floor"] = meta["floor"]
    return out


# ── Risk scoring ──────────────────────────────────────────────────────────────

def _score_machine(meta: dict, state: dict) -> MachineRisk:
    safe_t  = meta["safe_temp"]
    safe_v  = meta["safe_vib"]
    temp    = max(state["temp"], 10.0)
    vib     = max(state["vib"], 0.0)
    energy  = state["energy"]
    workers = state["workers_present"]
    mid     = meta["id"]

    # ── Classical rule-based scores ──────────────────────────────────────────
    fire    = min(100.0, max(0.0, ((temp / safe_t) - 0.5) * 200))
    failure = min(100.0, max(0.0, ((vib  / safe_v) - 0.4) * 200))
    intrusion = (60.0 + random.uniform(-5, 15)
                 if meta["zone"] in RESTRICTED_ZONES and workers else 0.0)
    worker_h  = min(100.0, fire * 0.4 + (30 if workers else 0))

    # ── ML Anomaly Detection (Isolation Forest + Z-score) ────────────────────
    ml_score = _ml.feed(mid, temp, vib, energy)
    z_score  = _ml.z_scores.get(mid, 0.0)
    ai_used  = ("Isolation Forest" if _ml.fitted.get(mid, False)
                else "Z-score (warming up…)")

    # ── Weighted Risk Fusion ─────────────────────────────────────────────────
    # Classical component: 60%
    # ML anomaly boost:    25%
    # Z-score boost:       15%
    classical = (
        fire       * 0.40 +
        failure    * 0.30 +
        intrusion  * 0.20 +
        worker_h   * 0.10
    )
    composite = classical * 0.60 + ml_score * 0.25 + z_score * 0.15

    # Context amplifier: worker + high fire = danger multiplier
    if workers and fire > 50:
        composite = min(100, composite * 1.25)

    score = round(min(100, max(0, composite)), 1)

    level = (
        "CRITICAL" if score >= 85 else
        "HIGH"     if score >= 65 else
        "MEDIUM"   if score >= 40 else
        "LOW"      if score >= 20 else
        "SAFE"
    )

    alerts = []
    if fire > 60:
        alerts.append(f"🔥 Temp {temp:.1f}°C – OVERHEAT DETECTED")
    if failure > 55:
        alerts.append(f"⚙️  Vibration {vib:.2f}g – FAILURE RISK")
    if intrusion > 50:
        alerts.append(f"🚷 Worker in RESTRICTED zone {meta['zone']}")
    if worker_h > 60:
        alerts.append("🏥 Worker health emergency – high temp exposure")
    if ml_score > 60:
        alerts.append(f"🤖 AI anomaly detected (IF score {ml_score:.0f}%)")
    if z_score > 70:
        alerts.append(f"📊 Statistical outlier detected (Z={z_score:.0f}%)")

    return MachineRisk(
        machine_id=mid,
        zone=meta["zone"],
        floor=meta["floor"],
        machine_type=meta["type"],
        temp=round(temp, 1),
        vibration=round(vib, 2),
        energy=round(energy, 1),
        workers_present=workers,
        fire_risk=round(fire, 1),
        intrusion_risk=round(intrusion, 1),
        failure_risk=round(failure, 1),
        worker_risk=round(worker_h, 1),
        ml_anomaly_score=ml_score,
        z_score=z_score,
        ai_method=ai_used,
        risk_score=score,
        risk_level=level,
        alerts=alerts,
    )


# ── Predictive forecast (time-series extrapolation) ──────────────────────────

def _build_forecast(machines: List[MachineRisk], global_score: float) -> List[dict]:
    """5-step probabilistic forecast (T+2min intervals) with trend modelling."""
    history = list(_ml.windows.get(machines[0].machine_id, []))
    # Compute trend direction from last 10 readings
    trend_bias = 0.0
    if len(history) >= 10:
        recent = [h[0] for h in history[-10:]]
        trend_bias = (recent[-1] - recent[0]) / 10 * 2   # °C/min → risk impact

    forecast = []
    score = global_score
    for i in range(5):
        delta = random.uniform(-2, 5) + max(0, trend_bias * 0.8)
        score = max(0, min(100, score + delta))
        mins  = (i + 1) * 2
        forecast.append({
            "t_plus_min":  mins,
            "score":       round(score, 1),
            "label":       f"T+{mins}min",
            "probability": round(min(95, 45 + score * 0.50), 1),
        })
    return forecast


# ── Emergency recommendation ──────────────────────────────────────────────────

def _recommend(global_score: float, machines: List[MachineRisk]) -> str:
    crit = [m.machine_id for m in machines if m.risk_level == "CRITICAL"]
    high = [m.machine_id for m in machines if m.risk_level == "HIGH"]
    if global_score >= 90:
        return f"🚨 EMERGENCY LOCKDOWN — Evacuate all zones. Shut down: {', '.join(crit) or 'ALL MACHINES'}. Contact emergency services."
    if global_score >= 75:
        return f"⚠️  HIGH ALERT — Dispatch technician to {(crit+high)[0] if (crit+high) else 'site'}. Notify supervisor immediately. Prepare evacuation."
    if global_score >= 50:
        return "🔶 MONITOR CLOSELY — Review sensor trends. Verify worker PPE. Prepare maintenance team."
    if global_score >= 25:
        return "🟡 ELEVATED — Routine check recommended within 30 min. Log current readings."
    return "✅ NOMINAL — All systems within safe parameters. Continuous monitoring active."


# ── Public API ────────────────────────────────────────────────────────────────

def inject_scenario(scenario: str, machine_id: Optional[str] = None):
    _sim.active_scenario  = scenario
    _sim.scenario_t       = time.time()
    _sim.scenario_machine = machine_id or MACHINES[0]["id"]


def clear_scenario():
    _sim.active_scenario  = None
    _sim.scenario_machine = ""


def compute_risk() -> RiskSnapshot:
    now = time.time()
    machine_risks = []
    raw_states = []

    for meta in MACHINES:
        state = _tick_machine(meta["id"], meta, now)
        raw_states.append(state)
        risk = _score_machine(meta, state)
        machine_risks.append(risk)

    # Weighted global score (top machines count more)
    scores  = sorted([m.risk_score for m in machine_risks], reverse=True)
    weights = [1.0 / (i + 1) for i in range(len(scores))]
    global_score = round(
        sum(s * w for s, w in zip(scores, weights)) / sum(weights), 1
    )

    global_level = (
        "CRITICAL" if global_score >= 85 else
        "HIGH"     if global_score >= 65 else
        "MEDIUM"   if global_score >= 40 else
        "LOW"      if global_score >= 20 else
        "SAFE"
    )

    # Emit agent messages for this cycle
    _emit_agent_messages(raw_states)

    # AI metadata for dashboard transparency panel
    n_fitted = sum(1 for mid in _ml.fitted if _ml.fitted[mid])
    ai_info = {
        "method":       "Isolation Forest (sklearn)" if SKLEARN_AVAILABLE else "Z-score Statistical",
        "models_ready": n_fitted,
        "total_models": len(MACHINES),
        "window_size":  _ml.MIN_SAMPLES,
        "contamination": 0.12,
        "features":     ["temperature", "vibration", "energy_kWh"],
        "fusion":       "Weighted multi-vector (Classical 60% + IF 25% + Z-score 15%)",
    }

    return RiskSnapshot(
        timestamp=datetime.now(_UTC).isoformat(),
        global_score=global_score,
        global_level=global_level,
        emergency_mode=bool(global_score >= 85),
        recommendation=_recommend(global_score, machine_risks),
        machines=machine_risks,
        predictions=_build_forecast(machine_risks, global_score),
        scenario=_sim.active_scenario,
        agent_messages=list(_sim.agent_messages)[:12],
        ai_info=ai_info,
    )
