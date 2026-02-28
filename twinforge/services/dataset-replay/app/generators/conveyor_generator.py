"""Conveyor belt data generator — produces realistic telemetry records."""

import random
from datetime import datetime, timezone


def generate_conveyor_record(machine_id: str = "CONV-001") -> dict:
    """Generate a single conveyor belt telemetry record."""
    speed = 1.2 + random.gauss(0, 0.2)
    temp = 35.0 + random.gauss(0, 3)
    vibration = 0.15 + random.gauss(0, 0.05)
    energy = 3.5 + random.gauss(0, 0.5)
    jam = random.random() < 0.02

    return {
        "machine_id": machine_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "machine_type": "Conveyor",
        "temperature": round(max(15, temp), 2),
        "vibration": round(max(0, vibration), 4),
        "energy_kwh": round(max(0, energy), 2),
        "water_liters": 0.0,
        "belt_speed_mps": round(max(0, speed), 3),
        "status": "failure" if jam else "running",
        "failure_flag": jam,
        "failure_risk_score": round(random.uniform(0.5, 0.85) if jam else random.uniform(0.01, 0.2), 3),
    }


def generate_conveyor_batch(count: int = 3, machine_ids: list[str] | None = None) -> list[dict]:
    """Generate a batch of conveyor telemetry records."""
    ids = machine_ids or [f"CONV-{i:03d}" for i in range(1, count + 1)]
    return [generate_conveyor_record(mid) for mid in ids]
