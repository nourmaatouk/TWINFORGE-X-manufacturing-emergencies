"""
TWINFORGE Agent 3 — Anomaly Detection Tests
Tests for threshold detection, rolling mean deviation, spike detection, and risk scoring.
"""

import pytest
from app.detection.anomaly_detector import AnomalyDetector
from app.models.schemas import MachineTelemetry, MachineStatus, AlertType, AlertSeverity


@pytest.fixture
def detector():
    """Create a fresh anomaly detector with default thresholds."""
    return AnomalyDetector(
        vibration_threshold=8.0,
        temperature_threshold=95.0,
        energy_spike_factor=2.0,
        water_spike_factor=2.5,
        window_size=30,
        deviation_multiplier=2.5,
    )


def _make_record(
    machine_id: str = "M1",
    energy: float = 10.0,
    water: float = 3.0,
    vibration: float = 2.0,
    temperature: float = 65.0,
    failure: bool = False,
) -> MachineTelemetry:
    """Helper to create telemetry records."""
    return MachineTelemetry(
        machine_id=machine_id,
        energy_kwh=energy,
        water_liters=water,
        vibration=vibration,
        temperature=temperature,
        status=MachineStatus.FAILURE if failure else MachineStatus.RUNNING,
        failure_flag=failure,
    )


class TestThresholdDetection:
    """Tests for rule-based threshold alerts."""

    def test_vibration_threshold(self, detector: AnomalyDetector):
        """High vibration should trigger an alert."""
        record = _make_record(vibration=10.0)
        alerts = detector.detect(record)
        vib_alerts = [a for a in alerts if a.alert_type == AlertType.VIBRATION_THRESHOLD]
        assert len(vib_alerts) == 1
        assert vib_alerts[0].severity in (AlertSeverity.HIGH, AlertSeverity.CRITICAL)

    def test_critical_vibration(self, detector: AnomalyDetector):
        """Very high vibration (>1.5x threshold) should be CRITICAL."""
        record = _make_record(vibration=15.0)
        alerts = detector.detect(record)
        vib_alerts = [a for a in alerts if a.alert_type == AlertType.VIBRATION_THRESHOLD]
        assert len(vib_alerts) == 1
        assert vib_alerts[0].severity == AlertSeverity.CRITICAL

    def test_normal_vibration(self, detector: AnomalyDetector):
        """Normal vibration should not trigger threshold alert."""
        record = _make_record(vibration=3.0)
        alerts = detector.detect(record)
        vib_alerts = [a for a in alerts if a.alert_type == AlertType.VIBRATION_THRESHOLD]
        assert len(vib_alerts) == 0

    def test_temperature_threshold(self, detector: AnomalyDetector):
        """High temperature should trigger an alert."""
        record = _make_record(temperature=100.0)
        alerts = detector.detect(record)
        temp_alerts = [a for a in alerts if a.alert_type == AlertType.TEMPERATURE_THRESHOLD]
        assert len(temp_alerts) == 1


class TestFailureDetection:
    """Tests for failure event detection."""

    def test_failure_flag(self, detector: AnomalyDetector):
        """Failure flag should trigger CRITICAL alert."""
        record = _make_record(failure=True)
        alerts = detector.detect(record)
        failure_alerts = [a for a in alerts if a.alert_type == AlertType.FAILURE_DETECTED]
        assert len(failure_alerts) == 1
        assert failure_alerts[0].severity == AlertSeverity.CRITICAL


class TestSpikeDetection:
    """Tests for energy/water spike detection."""

    def test_energy_spike_after_warmup(self, detector: AnomalyDetector):
        """Energy spike after filling the rolling window should trigger alert."""
        # Fill rolling window with normal values
        for _ in range(10):
            detector.detect(_make_record(energy=10.0))

        # Send a spike
        spike_record = _make_record(energy=25.0)  # 2.5x the mean
        alerts = detector.detect(spike_record)
        spike_alerts = [a for a in alerts if a.alert_type == AlertType.ENERGY_SPIKE]
        assert len(spike_alerts) == 1

    def test_no_spike_during_warmup(self, detector: AnomalyDetector):
        """No spike alert when window is too small."""
        record = _make_record(energy=25.0)
        alerts = detector.detect(record)
        spike_alerts = [a for a in alerts if a.alert_type == AlertType.ENERGY_SPIKE]
        assert len(spike_alerts) == 0


class TestFailureRiskScoring:
    """Tests for failure probability scoring."""

    def test_low_risk(self, detector: AnomalyDetector):
        """Normal readings should have low risk score."""
        record = _make_record(vibration=2.0, temperature=65.0)
        score = detector.compute_failure_risk(record)
        assert score < 0.5

    def test_high_risk(self, detector: AnomalyDetector):
        """High vibration + temperature + failure should give high risk."""
        record = _make_record(vibration=9.0, temperature=100.0, failure=True)
        score = detector.compute_failure_risk(record)
        assert score > 0.6

    def test_risk_capped_at_one(self, detector: AnomalyDetector):
        """Risk score should never exceed 1.0."""
        record = _make_record(vibration=50.0, temperature=200.0, energy=100.0, failure=True)
        score = detector.compute_failure_risk(record)
        assert score <= 1.0
