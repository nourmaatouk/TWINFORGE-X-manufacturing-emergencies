"""
TWINFORGE Agent 3 — Anomaly Detector
Lightweight real-time anomaly detection for industrial telemetry.

Implements:
  - Rule-based threshold detection
  - Rolling mean deviation (sliding window)
  - Spike detection
  - Failure probability scoring
"""

import logging
import uuid
from collections import deque
from datetime import datetime
from typing import Optional

from app.config import settings
from app.models.schemas import AlertSeverity, AlertType, AnomalyAlert, MachineTelemetry

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Real-time anomaly detection engine.

    Maintains per-machine rolling windows for deviation analysis and
    applies configurable threshold rules to each incoming telemetry point.
    """

    def __init__(
        self,
        vibration_threshold: float = settings.VIBRATION_THRESHOLD,
        temperature_threshold: float = settings.TEMPERATURE_THRESHOLD,
        energy_spike_factor: float = settings.ENERGY_SPIKE_FACTOR,
        water_spike_factor: float = settings.WATER_SPIKE_FACTOR,
        window_size: int = settings.ROLLING_WINDOW_SIZE,
        deviation_multiplier: float = settings.DEVIATION_MULTIPLIER,
    ) -> None:
        self.vibration_threshold = vibration_threshold
        self.temperature_threshold = temperature_threshold
        self.energy_spike_factor = energy_spike_factor
        self.water_spike_factor = water_spike_factor
        self.window_size = window_size
        self.deviation_multiplier = deviation_multiplier

        # Per-machine rolling windows: machine_id -> deque of values
        self._energy_windows: dict[str, deque[float]] = {}
        self._water_windows: dict[str, deque[float]] = {}
        self._vibration_windows: dict[str, deque[float]] = {}
        self._temperature_windows: dict[str, deque[float]] = {}

    def detect(self, record: MachineTelemetry) -> list[AnomalyAlert]:
        """
        Run all anomaly detection checks on a telemetry record.

        Returns a list of triggered alerts (may be empty).
        """
        alerts: list[AnomalyAlert] = []
        mid = record.machine_id

        # Initialize windows if new machine
        if mid not in self._energy_windows:
            self._energy_windows[mid] = deque(maxlen=self.window_size)
            self._water_windows[mid] = deque(maxlen=self.window_size)
            self._vibration_windows[mid] = deque(maxlen=self.window_size)
            self._temperature_windows[mid] = deque(maxlen=self.window_size)

        # ─── Rule-Based Threshold Checks ─────────────────────────────────

        # Vibration threshold
        if record.vibration > self.vibration_threshold:
            severity = AlertSeverity.CRITICAL if record.vibration > self.vibration_threshold * 1.5 else AlertSeverity.HIGH
            alerts.append(self._create_alert(
                machine_id=mid,
                alert_type=AlertType.VIBRATION_THRESHOLD,
                severity=severity,
                value=record.vibration,
                threshold=self.vibration_threshold,
                message=f"Vibration {record.vibration:.2f} exceeds threshold {self.vibration_threshold}",
            ))

        # Temperature threshold
        if record.temperature > self.temperature_threshold:
            severity = AlertSeverity.CRITICAL if record.temperature > self.temperature_threshold * 1.1 else AlertSeverity.HIGH
            alerts.append(self._create_alert(
                machine_id=mid,
                alert_type=AlertType.TEMPERATURE_THRESHOLD,
                severity=severity,
                value=record.temperature,
                threshold=self.temperature_threshold,
                message=f"Temperature {record.temperature:.1f}°C exceeds threshold {self.temperature_threshold}°C",
            ))

        # ─── Spike Detection (Rolling Mean Deviation) ────────────────────

        energy_alert = self._check_spike(
            value=record.energy_kwh,
            window=self._energy_windows[mid],
            spike_factor=self.energy_spike_factor,
            machine_id=mid,
            alert_type=AlertType.ENERGY_SPIKE,
            field_name="energy_kwh",
            unit="kWh",
        )
        if energy_alert:
            alerts.append(energy_alert)

        water_alert = self._check_spike(
            value=record.water_liters,
            window=self._water_windows[mid],
            spike_factor=self.water_spike_factor,
            machine_id=mid,
            alert_type=AlertType.WATER_SPIKE,
            field_name="water_liters",
            unit="L",
        )
        if water_alert:
            alerts.append(water_alert)

        # ─── Rolling Mean Deviation (vibration & temperature) ────────────

        vib_dev_alert = self._check_rolling_deviation(
            value=record.vibration,
            window=self._vibration_windows[mid],
            machine_id=mid,
            field_name="vibration",
        )
        if vib_dev_alert:
            alerts.append(vib_dev_alert)

        temp_dev_alert = self._check_rolling_deviation(
            value=record.temperature,
            window=self._temperature_windows[mid],
            machine_id=mid,
            field_name="temperature",
        )
        if temp_dev_alert:
            alerts.append(temp_dev_alert)

        # ─── Failure Detection ───────────────────────────────────────────

        if record.failure_flag:
            alerts.append(self._create_alert(
                machine_id=mid,
                alert_type=AlertType.FAILURE_DETECTED,
                severity=AlertSeverity.CRITICAL,
                value=1.0,
                threshold=0.0,
                message=f"Failure event detected on machine {mid}",
                risk_score=1.0,
            ))

        # Failure prediction
        risk_score = self.compute_failure_risk(record)
        if risk_score > 0.7:
            alerts.append(self._create_alert(
                machine_id=mid,
                alert_type=AlertType.FAILURE_PREDICTED,
                severity=AlertSeverity.HIGH if risk_score > 0.85 else AlertSeverity.MEDIUM,
                value=risk_score,
                threshold=0.7,
                message=f"High failure risk ({risk_score:.2f}) predicted for machine {mid}",
                risk_score=risk_score,
            ))

        # ─── Update Windows ──────────────────────────────────────────────

        self._energy_windows[mid].append(record.energy_kwh)
        self._water_windows[mid].append(record.water_liters)
        self._vibration_windows[mid].append(record.vibration)
        self._temperature_windows[mid].append(record.temperature)

        if alerts:
            logger.info("Detected %d anomalies on machine %s", len(alerts), mid)

        return alerts

    def compute_failure_risk(self, record: MachineTelemetry) -> float:
        """
        Compute a failure probability score [0.0 - 1.0] based on current readings.

        Scoring factors:
        - Vibration proximity to threshold: 0-0.3
        - Temperature proximity to threshold: 0-0.3
        - Energy anomaly: 0-0.2
        - Explicit failure flag: 0.2
        """
        score = 0.0

        # Vibration factor
        if record.vibration > 0:
            vib_ratio = record.vibration / self.vibration_threshold
            score += min(vib_ratio * 0.3, 0.3)

        # Temperature factor
        if record.temperature > 0:
            temp_ratio = record.temperature / self.temperature_threshold
            score += min(temp_ratio * 0.3, 0.3)

        # Energy anomaly factor
        mid = record.machine_id
        if mid in self._energy_windows and len(self._energy_windows[mid]) > 5:
            mean = sum(self._energy_windows[mid]) / len(self._energy_windows[mid])
            if mean > 0 and record.energy_kwh > mean * self.energy_spike_factor:
                score += 0.2

        # Failure flag
        if record.failure_flag:
            score += 0.2

        return min(score, 1.0)

    def _check_spike(
        self,
        value: float,
        window: deque[float],
        spike_factor: float,
        machine_id: str,
        alert_type: AlertType,
        field_name: str,
        unit: str,
    ) -> Optional[AnomalyAlert]:
        """Check if a value represents a spike relative to the rolling mean."""
        if len(window) < 5:
            return None

        mean = sum(window) / len(window)
        if mean <= 0:
            return None

        if value > mean * spike_factor:
            return self._create_alert(
                machine_id=machine_id,
                alert_type=alert_type,
                severity=AlertSeverity.HIGH,
                value=value,
                threshold=mean * spike_factor,
                message=f"{field_name} spike: {value:.2f}{unit} vs rolling mean {mean:.2f}{unit} (factor {spike_factor}x)",
            )
        return None

    def _check_rolling_deviation(
        self,
        value: float,
        window: deque[float],
        machine_id: str,
        field_name: str,
    ) -> Optional[AnomalyAlert]:
        """Check if a value deviates significantly from the rolling mean."""
        if len(window) < 10:
            return None

        values = list(window)
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = variance ** 0.5

        if std_dev <= 0:
            return None

        deviation = abs(value - mean) / std_dev
        if deviation > self.deviation_multiplier:
            return self._create_alert(
                machine_id=machine_id,
                alert_type=AlertType.ROLLING_DEVIATION,
                severity=AlertSeverity.MEDIUM,
                value=value,
                threshold=mean + self.deviation_multiplier * std_dev,
                message=f"{field_name} deviation {deviation:.1f}σ from rolling mean ({mean:.2f} ± {std_dev:.2f})",
            )
        return None

    @staticmethod
    def _create_alert(
        machine_id: str,
        alert_type: AlertType,
        severity: AlertSeverity,
        value: float,
        threshold: float,
        message: str,
        risk_score: float = 0.0,
    ) -> AnomalyAlert:
        """Create an AnomalyAlert instance."""
        return AnomalyAlert(
            alert_id=f"ALR-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(),
            machine_id=machine_id,
            alert_type=alert_type,
            severity=severity,
            value=value,
            threshold=threshold,
            message=message,
            failure_risk_score=risk_score,
        )
