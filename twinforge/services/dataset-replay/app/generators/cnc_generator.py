"""CNC Machine data generator — produces realistic telemetry records."""

import random
from datetime import datetime, timezone


def generate_cnc_record(machine_id: str = "CNC-001") -> dict:
    """Generate a single CNC machine telemetry record."""
    base_temp = 55.0 + random.gauss(0, 5)
    base_vibration = 0.4 + random.gauss(0, 0.1)
    energy = 12.0 + random.gauss(0, 2)
    spindle_speed = 8000 + random.gauss(0, 500)
    failure_flag = random.random() < 0.03

    return {
        "machine_id": machine_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "machine_type": "CNC",
        "temperature": round(max(20, base_temp), 2),
        "vibration": round(max(0, base_vibration), 4),
        "energy_kwh": round(max(0, energy), 2),
        "water_liters": round(random.uniform(0.5, 3.0), 2),
        "spindle_speed_rpm": round(max(0, spindle_speed)),
        "status": "failure" if failure_flag else "running",
        "failure_flag": failure_flag,
        "failure_risk_score": round(random.uniform(0.6, 0.95) if failure_flag else random.uniform(0.01, 0.3), 3),
    }


def generate_cnc_batch(count: int = 5, machine_ids: list[str] | None = None) -> list[dict]:
    """Generate a batch of CNC telemetry records."""
    ids = machine_ids or [f"CNC-{i:03d}" for i in range(1, count + 1)]
    return [generate_cnc_record(mid) for mid in ids]
