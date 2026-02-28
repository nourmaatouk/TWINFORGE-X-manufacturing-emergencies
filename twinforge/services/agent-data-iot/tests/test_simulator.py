"""
TWINFORGE Agent 3 — Simulation Engine Tests
Tests for the simulation engine output format, value ranges, and concurrent safety.
"""

import asyncio
import pytest
import pytest_asyncio
from app.models.schemas import MachineTelemetry, MachineStatus, SimulationConfig
from app.simulation.simulation_engine import SimulationEngine, load_dataset_csv


class TestSimulationEngine:
    """Tests for the simulation engine."""

    @pytest.mark.asyncio
    async def test_generates_telemetry(self):
        """Simulation should produce telemetry records."""
        collected: list[list[MachineTelemetry]] = []

        async def collect(records: list[MachineTelemetry]):
            collected.append(records)

        config = SimulationConfig(
            number_of_machines=2,
            simulation_duration_hours=0.001,  # ~3.6 seconds
            sampling_interval_seconds=1,
        )
        engine = SimulationEngine(config=config, on_telemetry=collect)
        await engine.run()

        assert len(collected) > 0
        assert engine.points_generated > 0

    @pytest.mark.asyncio
    async def test_correct_machine_count(self):
        """Each tick should produce one record per machine."""
        collected: list[list[MachineTelemetry]] = []

        async def collect(records: list[MachineTelemetry]):
            collected.append(records)

        config = SimulationConfig(
            number_of_machines=3,
            simulation_duration_hours=0.001,
            sampling_interval_seconds=1,
        )
        engine = SimulationEngine(config=config, on_telemetry=collect)
        await engine.run()

        if collected:
            assert len(collected[0]) == 3  # 3 machines per tick

    @pytest.mark.asyncio
    async def test_telemetry_format(self):
        """Each record should have valid fields and ranges."""
        collected: list[MachineTelemetry] = []

        async def collect(records: list[MachineTelemetry]):
            collected.extend(records)

        config = SimulationConfig(
            number_of_machines=2,
            simulation_duration_hours=0.001,
            sampling_interval_seconds=1,
        )
        engine = SimulationEngine(config=config, on_telemetry=collect)
        await engine.run()

        for record in collected:
            assert record.machine_id.startswith("M")
            assert record.energy_kwh >= 0
            assert record.water_liters >= 0
            assert record.vibration >= 0
            assert 0.0 <= record.failure_risk_score <= 1.0
            assert record.status in MachineStatus

    @pytest.mark.asyncio
    async def test_stop_simulation(self):
        """Simulation should stop when stop() is called."""
        config = SimulationConfig(
            number_of_machines=1,
            simulation_duration_hours=1.0,  # long duration
            sampling_interval_seconds=1,
        )
        engine = SimulationEngine(config=config)

        task = asyncio.create_task(engine.run())
        await asyncio.sleep(0.5)
        engine.stop()
        await asyncio.sleep(0.5)

        assert not engine.is_running


class TestDatasetCSVLoader:
    """Tests for CSV dataset loading."""

    def test_parse_csv(self):
        """Test parsing a CSV string."""
        csv_content = """machine_id,energy_kwh,water_liters,vibration,temperature,status,failure_flag
M1,12.5,3.2,2.1,68.5,running,false
M2,10.8,2.8,1.9,65.2,running,false
M3,2.0,0.3,1.0,55.0,failure,true"""

        records = load_dataset_csv(csv_content)
        assert len(records) == 3
        assert records[0]["machine_id"] == "M1"
        assert records[0]["energy_kwh"] == 12.5
        assert records[2]["failure_flag"] is True

    def test_empty_csv(self):
        """Test parsing empty CSV."""
        csv_content = "machine_id,energy_kwh,water_liters,vibration,temperature,status,failure_flag\n"
        records = load_dataset_csv(csv_content)
        assert len(records) == 0
