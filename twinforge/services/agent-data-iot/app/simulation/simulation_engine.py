"""
TWINFORGE Agent 3 — Simulation Engine
Generates realistic industrial telemetry over configurable durations.

Features:
  - Cyclic production patterns (shift-based)
  - Correlated water/energy usage
  - Noise injection with smooth variations
  - Load ramp-up / ramp-down transitions
  - Failure simulation: energy spike → vibration increase → downtime → recovery
  - Configurable anomaly frequency, machine count, sampling interval
  - Concurrent-safe, runs as asyncio background task
"""

import asyncio
import csv
import io
import logging
import math
import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Optional

from app.models.schemas import MachineTelemetry, MachineStatus, SimulationConfig

logger = logging.getLogger(__name__)


# ─── Machine Profile ────────────────────────────────────────────────────────

class MachineProfile:
    """State for a single simulated machine."""

    def __init__(self, machine_id: str, intensity: float = 0.7) -> None:
        self.machine_id = machine_id
        self.base_energy = random.uniform(8.0, 15.0)
        self.base_water = random.uniform(1.5, 5.0)
        self.base_vibration = random.uniform(1.0, 3.0)
        self.base_temperature = random.uniform(55.0, 70.0)
        self.intensity = intensity

        # State tracking
        self.status = MachineStatus.RUNNING
        self.failure_flag = False
        self.failure_cooldown = 0  # seconds remaining in failure
        self.recovery_progress = 0.0  # 0.0 to 1.0
        self.is_recovering = False
        self.pre_failure_countdown = 0  # seconds of degradation before failure
        self.cycle_offset = random.uniform(0, 2 * math.pi)  # phase offset


# ─── Simulation Engine ──────────────────────────────────────────────────────

class SimulationEngine:
    """
    Generates realistic industrial telemetry for multiple machines.

    The engine runs as an async background task, producing telemetry
    at the configured sampling interval and feeding it through a callback
    (typically the agent's ingestion pipeline).
    """

    def __init__(
        self,
        config: SimulationConfig,
        on_telemetry: Optional[Callable[[list[MachineTelemetry]], Coroutine[Any, Any, Any]]] = None,
    ) -> None:
        self.config = config
        self.simulation_id = f"SIM-{uuid.uuid4().hex[:8]}"
        self._on_telemetry = on_telemetry
        self._running = False
        self._points_generated = 0
        self._started_at: Optional[datetime] = None
        self._machines: list[MachineProfile] = []

    async def run(self) -> None:
        """
        Main simulation loop.

        Generates telemetry for all machines at each tick, applying
        realistic industrial patterns including shift cycles, failures,
        and correlated sensor readings.
        """
        self._running = True
        self._started_at = datetime.now()
        self._machines = [
            MachineProfile(f"M{i+1}", self.config.production_intensity_level)
            for i in range(self.config.number_of_machines)
        ]

        total_seconds = int(self.config.simulation_duration_hours * 3600)
        interval = self.config.sampling_interval_seconds

        logger.info(
            "Simulation %s started: %d machines, %d seconds, %ds interval",
            self.simulation_id,
            len(self._machines),
            total_seconds,
            interval,
        )

        sim_time = datetime.now()
        elapsed = 0

        try:
            while elapsed < total_seconds and self._running:
                records: list[MachineTelemetry] = []

                for machine in self._machines:
                    record = self._generate_tick(machine, elapsed, total_seconds, sim_time)
                    records.append(record)
                    self._points_generated += 1

                # Feed through callback
                if self._on_telemetry and records:
                    try:
                        await self._on_telemetry(records)
                    except Exception as e:
                        logger.error("Simulation telemetry callback error: %s", e)

                elapsed += interval
                sim_time += timedelta(seconds=interval)
                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logger.info("Simulation %s cancelled", self.simulation_id)
        finally:
            self._running = False
            logger.info(
                "Simulation %s ended: %d points generated",
                self.simulation_id,
                self._points_generated,
            )

    def stop(self) -> None:
        """Stop the simulation."""
        self._running = False

    def _generate_tick(
        self,
        machine: MachineProfile,
        elapsed: int,
        total_seconds: int,
        sim_time: datetime,
    ) -> MachineTelemetry:
        """Generate a single telemetry tick for one machine."""

        # ─── Time-based factors ──────────────────────────────────────────
        progress = elapsed / max(total_seconds, 1)
        hour_of_day = (elapsed / 3600) % 24

        # Shift cycle: peak during working hours (6-22), idle at night
        shift_factor = self._shift_pattern(hour_of_day)

        # Production cycle: sinusoidal with machine-specific phase
        cycle_factor = 0.5 + 0.5 * math.sin(
            2 * math.pi * elapsed / 1800 + machine.cycle_offset
        )

        # Ramp-up at start, ramp-down at end
        ramp = self._ramp_factor(progress)

        # Combined intensity
        intensity = machine.intensity * shift_factor * cycle_factor * ramp

        # ─── Handle failure states ───────────────────────────────────────

        if machine.pre_failure_countdown > 0:
            # Degradation phase: increasing vibration and energy before failure
            deg_progress = 1.0 - (machine.pre_failure_countdown / 30)
            machine.pre_failure_countdown -= self.config.sampling_interval_seconds

            if machine.pre_failure_countdown <= 0:
                # Trigger failure
                machine.status = MachineStatus.FAILURE
                machine.failure_flag = True
                machine.failure_cooldown = random.randint(60, 300)
                machine.pre_failure_countdown = 0
            else:
                # Pre-failure degradation readings
                return self._pre_failure_reading(machine, sim_time, intensity, deg_progress)

        elif machine.failure_cooldown > 0:
            # During failure: minimal consumption, high vibration
            machine.failure_cooldown -= self.config.sampling_interval_seconds
            if machine.failure_cooldown <= 0:
                machine.is_recovering = True
                machine.recovery_progress = 0.0
                machine.failure_flag = False
                machine.status = MachineStatus.STARTING
            return self._failure_reading(machine, sim_time)

        elif machine.is_recovering:
            # Recovery phase: gradual return to normal
            machine.recovery_progress += 0.05
            if machine.recovery_progress >= 1.0:
                machine.is_recovering = False
                machine.status = MachineStatus.RUNNING
                machine.recovery_progress = 1.0
            return self._recovery_reading(machine, sim_time, intensity)

        else:
            # Normal operation: check for random failure trigger
            if random.random() < self.config.anomaly_frequency * self.config.sampling_interval_seconds / 3600:
                machine.pre_failure_countdown = 30  # 30 seconds of degradation
                machine.status = MachineStatus.RUNNING

            # Idle detection
            if intensity < 0.15:
                machine.status = MachineStatus.IDLE
            else:
                machine.status = MachineStatus.RUNNING

        # ─── Normal readings ─────────────────────────────────────────────

        noise_e = random.gauss(0, 0.3)
        noise_w = random.gauss(0, 0.15)
        noise_v = random.gauss(0, 0.2)
        noise_t = random.gauss(0, 0.5)

        energy = max(0, machine.base_energy * intensity + noise_e)
        water = max(0, machine.base_water * intensity * 0.8 + noise_w)  # correlated
        vibration = max(0, machine.base_vibration * (0.5 + intensity * 0.5) + noise_v)
        temperature = machine.base_temperature + intensity * 20 + noise_t

        risk_score = self._compute_risk_score(vibration, temperature, energy, machine)

        return MachineTelemetry(
            timestamp=sim_time,
            machine_id=machine.machine_id,
            energy_kwh=round(energy, 2),
            water_liters=round(water, 2),
            vibration=round(vibration, 2),
            temperature=round(temperature, 1),
            status=machine.status,
            failure_flag=False,
            failure_risk_score=round(risk_score, 3),
        )

    def _pre_failure_reading(
        self, machine: MachineProfile, sim_time: datetime, intensity: float, deg_progress: float
    ) -> MachineTelemetry:
        """Generate readings during pre-failure degradation."""
        energy = machine.base_energy * intensity * (1 + deg_progress * 0.8) + random.gauss(0, 0.5)
        vibration = machine.base_vibration * (1 + deg_progress * 3.0) + random.gauss(0, 0.3)
        temperature = machine.base_temperature + 25 + deg_progress * 15 + random.gauss(0, 1.0)
        water = machine.base_water * intensity * 0.8 + random.gauss(0, 0.2)

        return MachineTelemetry(
            timestamp=sim_time,
            machine_id=machine.machine_id,
            energy_kwh=round(max(0, energy), 2),
            water_liters=round(max(0, water), 2),
            vibration=round(max(0, vibration), 2),
            temperature=round(temperature, 1),
            status=MachineStatus.RUNNING,
            failure_flag=False,
            failure_risk_score=round(min(0.5 + deg_progress * 0.5, 1.0), 3),
        )

    @staticmethod
    def _failure_reading(machine: MachineProfile, sim_time: datetime) -> MachineTelemetry:
        """Generate readings during an active failure."""
        return MachineTelemetry(
            timestamp=sim_time,
            machine_id=machine.machine_id,
            energy_kwh=round(random.uniform(0.5, 2.0), 2),  # minimal consumption
            water_liters=round(random.uniform(0.0, 0.5), 2),
            vibration=round(random.uniform(0.5, 1.5), 2),  # residual vibration
            temperature=round(machine.base_temperature - 10 + random.gauss(0, 2), 1),  # cooling
            status=MachineStatus.FAILURE,
            failure_flag=True,
            failure_risk_score=1.0,
        )

    def _recovery_reading(
        self, machine: MachineProfile, sim_time: datetime, intensity: float
    ) -> MachineTelemetry:
        """Generate readings during post-failure recovery (gradual ramp)."""
        rp = machine.recovery_progress
        energy = machine.base_energy * intensity * rp + random.gauss(0, 0.2)
        water = machine.base_water * intensity * rp * 0.8 + random.gauss(0, 0.1)
        vibration = machine.base_vibration * (0.5 + rp * 0.5) + random.gauss(0, 0.15)
        temperature = machine.base_temperature + rp * intensity * 15 + random.gauss(0, 0.5)

        return MachineTelemetry(
            timestamp=sim_time,
            machine_id=machine.machine_id,
            energy_kwh=round(max(0, energy), 2),
            water_liters=round(max(0, water), 2),
            vibration=round(max(0, vibration), 2),
            temperature=round(temperature, 1),
            status=MachineStatus.STARTING,
            failure_flag=False,
            failure_risk_score=round(max(0, 0.5 - rp * 0.4), 3),
        )

    @staticmethod
    def _shift_pattern(hour: float) -> float:
        """Simulate a day/night shift pattern."""
        if 6 <= hour < 14:
            return 0.9 + 0.1 * math.sin(math.pi * (hour - 6) / 8)  # morning shift
        elif 14 <= hour < 22:
            return 0.85 + 0.1 * math.sin(math.pi * (hour - 14) / 8)  # evening shift
        else:
            return 0.15 + 0.05 * random.random()  # night / idle

    @staticmethod
    def _ramp_factor(progress: float) -> float:
        """Ramp up at start, ramp down at end."""
        if progress < 0.05:
            return progress / 0.05  # 0 → 1 in first 5%
        elif progress > 0.95:
            return (1.0 - progress) / 0.05  # 1 → 0 in last 5%
        return 1.0

    def _compute_risk_score(
        self, vibration: float, temperature: float, energy: float, machine: MachineProfile
    ) -> float:
        """Lightweight failure risk from current readings."""
        score = 0.0
        if vibration > machine.base_vibration * 2:
            score += 0.3
        if temperature > machine.base_temperature + 30:
            score += 0.3
        if energy > machine.base_energy * 1.8:
            score += 0.2
        return min(score, 1.0)

    # ─── Status ──────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def points_generated(self) -> int:
        return self._points_generated

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at


# ─── CSV Dataset Loader ─────────────────────────────────────────────────────

def load_dataset_csv(csv_content: str) -> list[dict[str, Any]]:
    """
    Parse a CSV dataset and return a list of dicts.

    Expected columns: machine_id, energy_kwh, water_liters, vibration,
    temperature, status, failure_flag
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    records: list[dict[str, Any]] = []
    for row in reader:
        records.append({
            "machine_id": row.get("machine_id", "M1"),
            "energy_kwh": float(row.get("energy_kwh", 10.0)),
            "water_liters": float(row.get("water_liters", 3.0)),
            "vibration": float(row.get("vibration", 2.0)),
            "temperature": float(row.get("temperature", 65.0)),
            "status": row.get("status", "running"),
            "failure_flag": row.get("failure_flag", "false").lower() in ("true", "1", "yes"),
        })
    return records
