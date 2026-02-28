"""Dataset Replay — Main entry point.

Continuously generates synthetic industrial telemetry data and
POSTs it to agent-data-iot's /ingest endpoint.
"""

import asyncio
import logging
import signal
import sys

from app.replay_engine import ReplayEngine

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the replay engine and run until interrupted."""
    engine = ReplayEngine()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, engine.stop)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    logger.info("Dataset Replay service starting")
    await engine.run()
    logger.info("Dataset Replay service stopped")


if __name__ == "__main__":
    asyncio.run(main())
