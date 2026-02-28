
import sys
import os
import asyncio
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from twinforge.graph.workflow import get_graph
from twinforge.core.logging_config import setup_logging

setup_logging("INFO")

message = "Create digital twins 2 floor , Create a CNC machine twin on floor 1, line A, 45 kWh, 3 spindles and Create a CNC machine twin on floor 1, line B, 90 kWh, 5 spindles"

async def run_test():
    print(f"Testing with message: {message}")
    graph = get_graph()
    try:
        # Run in thread as in server.py
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(None, graph.invoke, message, "test_session")
        print("Success!")
        print(state)
    except Exception as e:
        print(f"Caught exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
