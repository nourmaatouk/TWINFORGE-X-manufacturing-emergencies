"""
TWINFORGE Agent 3 — Schema Tests
Tests for Pydantic model validation.
"""

import pytest
from datetime import datetime
from app.models.schemas import (
    MachineTelemetry,
    MachineStatus,
    SimulationConfig,
    AnomalyAlert,
    AlertSeverity,
    AlertType,
    TelemetryIngest,
)


class TestMachineTelemetry:
    """Tests for the MachineTelemetry model."""

    def test_valid_telemetry(self):
        """Test creating a valid telemetry record."""
        record = MachineTelemetry(
            machine_id="M1",
            energy_kwh=12.4,
            water_liters=3.1,
            vibration=2.5,
            temperature=75.2,
        )
        assert record.machine_id == "M1"
        assert record.energy_kwh == 12.4
        assert record.status == MachineStatus.RUNNING
        assert record.failure_flag is False
        assert 0.0 <= record.failure_risk_score <= 1.0

    def test_all_fields(self):
        """Test creating a telemetry record with all fields."""
        record = MachineTelemetry(
            timestamp=datetime(2026, 2, 18, 17, 0, 0),
            machine_id="M3",
            energy_kwh=25.0,
            water_liters=8.5,
            vibration=9.0,
            temperature=88.0,
            status=MachineStatus.FAILURE,
            failure_flag=True,
            failure_risk_score=0.95,
        )
        assert record.failure_flag is True
        assert record.status == MachineStatus.FAILURE
        assert record.failure_risk_score == 0.95

    def test_negative_energy_rejected(self):
        """Test that negative energy is rejected."""
        with pytest.raises(Exception):
            MachineTelemetry(
                machine_id="M1",
                energy_kwh=-5.0,
                water_liters=3.0,
                vibration=2.0,
                temperature=70.0,
            )

    def test_risk_score_out_of_range(self):
        """Test that risk score > 1.0 is rejected."""
        with pytest.raises(Exception):
            MachineTelemetry(
                machine_id="M1",
                energy_kwh=10.0,
                water_liters=3.0,
                vibration=2.0,
                temperature=70.0,
                failure_risk_score=1.5,
            )

    def test_json_serialization(self):
        """Test JSON round-trip."""
        record = MachineTelemetry(
            machine_id="M2",
            energy_kwh=10.0,
            water_liters=2.5,
            vibration=1.5,
            temperature=65.0,
        )
        json_data = record.model_dump(mode="json")
        assert json_data["machine_id"] == "M2"
        assert json_data["energy_kwh"] == 10.0


class TestSimulationConfig:
    """Tests for SimulationConfig model."""

    def test_defaults(self):
        """Test default simulation config values."""
        config = SimulationConfig()
        assert config.number_of_machines == 5
        assert config.simulation_duration_hours == 4.0
        assert config.sampling_interval_seconds == 5

    def test_custom_values(self):
        """Test custom simulation config."""
        config = SimulationConfig(
            number_of_machines=3,
            simulation_duration_hours=0.5,
            sampling_interval_seconds=2,
            anomaly_frequency=0.1,
            production_intensity_level=0.9,
        )
        assert config.number_of_machines == 3
        assert config.production_intensity_level == 0.9

    def test_too_many_machines(self):
        """Test that > 20 machines is rejected."""
        with pytest.raises(Exception):
            SimulationConfig(number_of_machines=25)


class TestTelemetryIngest:
    """Tests for TelemetryIngest batch model."""

    def test_valid_batch(self):
        """Test valid batch ingestion payload."""
        batch = TelemetryIngest(data=[
            MachineTelemetry(machine_id="M1", energy_kwh=10, water_liters=3, vibration=2, temperature=70),
            MachineTelemetry(machine_id="M2", energy_kwh=12, water_liters=4, vibration=3, temperature=75),
        ])
        assert len(batch.data) == 2

    def test_empty_batch_rejected(self):
        """Test that empty batch is rejected."""
        with pytest.raises(Exception):
            TelemetryIngest(data=[])


class TestAnomalyAlert:
    """Tests for AnomalyAlert model."""

    def test_create_alert(self):
        """Test creating an anomaly alert."""
        alert = AnomalyAlert(
            alert_id="ALR-test123",
            machine_id="M1",
            alert_type=AlertType.VIBRATION_THRESHOLD,
            severity=AlertSeverity.HIGH,
            value=10.5,
            threshold=8.0,
            message="Vibration exceeded threshold",
        )
        assert alert.severity == AlertSeverity.HIGH
        assert alert.value == 10.5
