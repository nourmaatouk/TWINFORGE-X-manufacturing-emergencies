"""
TWINFORGE Agent 3 — InfluxDB Storage
Async client for writing and querying time-series telemetry data.
"""

import logging
from datetime import datetime
from typing import Optional

from app.models.schemas import MachineTelemetry

logger = logging.getLogger(__name__)


class InfluxDBStorage:
    """
    InfluxDB 2.x async client for telemetry storage and retrieval.

    Provides write and query operations for machine telemetry data.
    Gracefully handles connection failures with fallback to no-op.
    """

    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "",
        org: str = "twinforge",
        bucket: str = "twinforge_sensors",
    ) -> None:
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self._client = None
        self._write_api = None
        self._query_api = None
        self._connected = False

    async def connect(self) -> None:
        """Initialize the InfluxDB client."""
        try:
            from influxdb_client import InfluxDBClient
            from influxdb_client.client.write_api import ASYNCHRONOUS

            self._client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self._write_api = self._client.write_api(write_options=ASYNCHRONOUS)
            self._query_api = self._client.query_api()
            self._connected = True
            logger.info("InfluxDB connected at %s", self.url)
        except ImportError:
            logger.warning("influxdb-client not installed, storage disabled")
        except Exception as e:
            logger.warning("InfluxDB connection failed: %s", e)

    async def disconnect(self) -> None:
        """Close the InfluxDB client."""
        if self._client:
            self._client.close()
            self._connected = False
        logger.info("InfluxDB disconnected")

    async def write_telemetry(self, record: MachineTelemetry) -> bool:
        """
        Write a single telemetry record to InfluxDB.

        Uses Point format with machine_id as tag for efficient querying.
        """
        if not self._connected or not self._write_api:
            return False

        try:
            from influxdb_client import Point

            point = (
                Point("machine_telemetry")
                .tag("machine_id", record.machine_id)
                .tag("status", record.status.value)
                .field("energy_kwh", float(record.energy_kwh))
                .field("water_liters", float(record.water_liters))
                .field("vibration", float(record.vibration))
                .field("temperature", float(record.temperature))
                .field("failure_flag", record.failure_flag)
                .field("failure_risk_score", float(record.failure_risk_score))
                .time(record.timestamp)
            )

            self._write_api.write(bucket=self.bucket, record=point)
            return True
        except Exception as e:
            logger.error("InfluxDB write error: %s", e)
            return False

    async def write_batch(self, records: list[MachineTelemetry]) -> int:
        """Write a batch of telemetry records. Returns count of successful writes."""
        count = 0
        for record in records:
            if await self.write_telemetry(record):
                count += 1
        return count

    async def query_latest(self, machine_id: Optional[str] = None) -> list[MachineTelemetry]:
        """Query the latest telemetry for each machine (or a specific machine)."""
        if not self._connected or not self._query_api:
            return []

        try:
            machine_filter = ""
            if machine_id:
                machine_filter = f'|> filter(fn: (r) => r.machine_id == "{machine_id}")'

            query = f'''
                from(bucket: "{self.bucket}")
                |> range(start: -1h)
                |> filter(fn: (r) => r._measurement == "machine_telemetry")
                {machine_filter}
                |> last()
                |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''

            result = self._query_api.query(query, org=self.org)
            return self._parse_flux_result(result)
        except Exception as e:
            logger.error("InfluxDB query error: %s", e)
            return []

    async def query_history(
        self,
        machine_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 100,
    ) -> list[MachineTelemetry]:
        """Query historical telemetry for a specific machine."""
        if not self._connected or not self._query_api:
            return []

        try:
            start_range = start or "-24h"
            end_range = f', stop: {end}' if end else ""

            query = f'''
                from(bucket: "{self.bucket}")
                |> range(start: {start_range}{end_range})
                |> filter(fn: (r) => r._measurement == "machine_telemetry")
                |> filter(fn: (r) => r.machine_id == "{machine_id}")
                |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> sort(columns: ["_time"], desc: true)
                |> limit(n: {limit})
            '''

            result = self._query_api.query(query, org=self.org)
            return self._parse_flux_result(result)
        except Exception as e:
            logger.error("InfluxDB history query error: %s", e)
            return []

    @staticmethod
    def _parse_flux_result(result: list) -> list[MachineTelemetry]:
        """Parse Flux query result tables into MachineTelemetry objects."""
        records: list[MachineTelemetry] = []
        for table in result:
            for row in table.records:
                try:
                    values = row.values
                    record = MachineTelemetry(
                        timestamp=values.get("_time", datetime.now()),
                        machine_id=values.get("machine_id", "unknown"),
                        energy_kwh=float(values.get("energy_kwh", 0)),
                        water_liters=float(values.get("water_liters", 0)),
                        vibration=float(values.get("vibration", 0)),
                        temperature=float(values.get("temperature", 0)),
                        status=values.get("status", "running"),
                        failure_flag=bool(values.get("failure_flag", False)),
                        failure_risk_score=float(values.get("failure_risk_score", 0)),
                    )
                    records.append(record)
                except Exception as e:
                    logger.warning("Failed to parse InfluxDB row: %s", e)
        return records

    @property
    def is_connected(self) -> bool:
        """Check if InfluxDB client is connected."""
        return self._connected
