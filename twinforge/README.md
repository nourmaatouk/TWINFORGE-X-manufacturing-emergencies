# TWINFORGE-X Core Risk Services (Python FastAPI)

This directory contains the Python backend that powers the TWINFORGE-X AI-Powered Industrial Risk Prevention & Emergency Intelligence dashboard. 

## Key Agent Implementation

The logic for multi-vector risk detection, Isolation Forest anomaly computation, forecast modelling, and simulated FIPA-ACL inter-agent communication resides in:

- **`services/Convesation_and_orchestrator_agents/twinforge/agents/risk_engine.py`**
  - Manages the entire `RiskSnapshot` lifecycle.
  - Implements the Scikit-learn **Isolation Forest** unsupervised learning model over sliding telemetry windows (temperature, vibration, energy).
  - Handles the fallback statistical Z-score mechanism.
  - Weights physical metrics (fire, failure) with spatial logic (hazard zone intrusion).

## Server Architecture

The WebSocket and REST API endpoints are located in:

- **`services/Convesation_and_orchestrator_agents/twinforge/dashboard/server.py`**
  - Exposes `ws://localhost:8001/ws/risk` to stream live JSON RiskSnapshots to the frontend.
  - Exposes `http://localhost:8001/api/risk/now` for synchronous fetching.
  - Exposes `POST /api/risk/scenario` to inject AI anomaly conditions (Overheat / Intrusion / Cascade / Clear).

## Dashboard UI Shell

The vanilla JS, HTML, and CSS powering the dashboard render inside `services/Convesation_and_orchestrator_agents/twinforge/dashboard/static/`.
It integrates completely into the overarching `Frontend/vite-project/` via an iFrame or direct port mapping.

## Dependencies

Required packages to run the predictive risk engine:
```sh
fastapi
uvicorn
websockets
scikit-learn
numpy
```

Make sure you are running a Python version >= 3.9.

### Execution

To run the risk backend and interactive demo shell, execute:
```sh
cd services/Convesation_and_orchestrator_agents
python run.py
```
