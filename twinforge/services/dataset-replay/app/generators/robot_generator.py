"""Robot arm data generator — produces realistic telemetry records."""

import random
from datetime import datetime, timezone


def generate_robot_record(machine_id: str = "ROB-001") -> dict:
    """Generate a single robot arm telemetry record."""
    temp = 42.0 + random.gauss(0, 4)
    vibration = 0.25 + random.gauss(0, 0.08)
    energy = 8.0 + random.gauss(0, 1.5)
    cycle_time = 4.5 + random.gauss(0, 0.5)
    collision = random.random() < 0.01

    return {
        "machine_id": machine_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "machine_type": "Robot",
        "temperature": round(max(20, temp), 2),
        "vibration": round(max(0, vibration), 4),
        "energy_kwh": round(max(0, energy), 2),
        "water_liters": round(random.uniform(0, 0.5), 2),
        "cycle_time_sec": round(max(1, cycle_time), 2),
        "status": "failure" if collision else "running",
        "failure_flag": collision,
        "failure_risk_score": round(random.uniform(0.7, 0.99) if collision else random.uniform(0.01, 0.15), 3),
    }


def generate_robot_batch(count: int = 3, machine_ids: list[str] | None = None) -> list[dict]:
    """Generate a batch of robot arm telemetry records."""
    ids = machine_ids or [f"ROB-{i:03d}" for i in range(1, count + 1)]
    return [generate_robot_record(mid) for mid in ids]
