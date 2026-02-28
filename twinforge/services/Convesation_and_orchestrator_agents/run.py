"""
TWINFORGE — Entry Point
Starts the FastAPI dashboard server with the full agent pipeline.
"""
import os
import sys
import uvicorn
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / ".env")


import multiprocessing
import time

def run_agent1():
    """Start Agent 1 (Dashboard + Conversation) on Port 8001."""
    import uvicorn
    uvicorn.run("twinforge.dashboard.server:app", host="0.0.0.0", port=8001, reload=False, log_level="info")

def run_agent2():
    """Start Agent 2 (Orchestrator) on Port 8002."""
    import uvicorn
    uvicorn.run("twinforge.agents.orchestrator.server:app", host="0.0.0.0", port=8002, reload=False, log_level="info")

def main():
    """Start the TWINFORGE platform."""
    from twinforge.core.config import get_settings
    from twinforge.core.logging_config import setup_logging

    settings = get_settings()
    setup_logging(settings.log_level)

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              TWINFORGE v1.0 — Blue Team                    ║")
    print("║     Conversational Manufacturing Digital Twin Platform     ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Groq LLM   : {'✅ ' + settings.groq_model if settings.groq_api_key else '❌ Not set'}                ║")
    print(f"║  Tenant     : {settings.tenant_id:<45}║")
    print(f"║  Log Level  : {settings.log_level:<45}║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Agent Ports:                                               ║")
    print("║    8001: Agent 1 (Conversation) + Dashboard                ║")
    print("║    8002: Agent 2 (Orchestrator)                            ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Dashboard → http://localhost:8001                         ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # Processes
    p2 = multiprocessing.Process(target=run_agent2)
    p2.start()
    
    # Wait for backend to be ready
    time.sleep(2)
    
    p1 = multiprocessing.Process(target=run_agent1)
    p1.start()

    try:
        p1.join()
        p2.join()
    except KeyboardInterrupt:
        print("\nStopping TwinForge...")
        p1.terminate()
        p2.terminate()


if __name__ == "__main__":
    main()
