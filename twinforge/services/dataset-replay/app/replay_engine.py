"""Replay Engine — generates and pushes telemetry batches to agent-data-iot."""

import asyncio
import logging

import httpx

from app.config import settings
from app.generators.cnc_generator import generate_cnc_batch
from app.generators.conveyor_generator import generate_conveyor_batch
from app.generators.robot_generator import generate_robot_batch

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Generates industrial telemetry and POSTs it to agent-data-iot's /ingest endpoint."""

    def __init__(self) -> None:
        self.target_url = f"{settings.AGENT_DATA_IOT_URL}/ingest"
        self.interval = settings.REPLAY_INTERVAL_SEC / settings.REPLAY_SPEED
        self.batch_size = settings.BATCH_SIZE
        self._running = False
        self._cycle_count = 0

    async def run(self) -> None:
        """Run the replay loop indefinitely."""
        self._running = True
        logger.info(
            "ReplayEngine started — target=%s interval=%.1fs batch=%d",
            self.target_url, self.interval, self.batch_size,
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            while self._running:
                try:
                    batch = self._generate_batch()
                    resp = await client.post(self.target_url, json={"data": batch})
                    self._cycle_count += 1

                    if resp.status_code == 200:
                        body = resp.json()
                        logger.info(
                            "Cycle %d: sent %d records — accepted=%d rejected=%d alerts=%d",
                            self._cycle_count, len(batch),
                            body.get("accepted", 0),
                            body.get("rejected", 0),
                            len(body.get("alerts", [])),
                        )
                    else:
                        logger.warning(
                            "Cycle %d: ingest returned %d — %s",
                            self._cycle_count, resp.status_code, resp.text[:200],
                        )
                except httpx.ConnectError:
                    logger.warning("agent-data-iot not reachable at %s, retrying...", self.target_url)
                except Exception as e:
                    logger.error("ReplayEngine error: %s", e)

                await asyncio.sleep(self.interval)

    def stop(self) -> None:
        """Stop the replay loop."""
        self._running = False

    def _generate_batch(self) -> list[dict]:
        """Generate a mixed batch of CNC, conveyor, and robot telemetry."""
        records: list[dict] = []
        records.extend(generate_cnc_batch(count=self.batch_size))
        records.extend(generate_conveyor_batch(count=max(1, self.batch_size // 2)))
        records.extend(generate_robot_batch(count=max(1, self.batch_size // 2)))
        return records
