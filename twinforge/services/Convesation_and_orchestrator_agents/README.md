# TWINFORGE-X AI-Powered Risk Intelligence Engine (Agent 6)

This microservice acts as the analytical core of the system and powers the primary dashboard of the TWINFORGE-X platform. It bridges data from the IoT gateways, security microservices, and verification agents. The backend is built on **FastAPI** to provide low latency streaming of complex multi-variate risk data.

## Goal

To directly address the ARSII challenge of creating an **AI-Powered Real-Time Industrial Risk Prevention & Emergency Intelligence** platform.

## Features Built for the Competition

### 1. Multi-Risk Detection Models
- **Thermal Tracking (🔥 Fire Risk):** Z-score deviation alerts on sudden temperature spikes. 
- **Equipment Failure (⚙️ Vibration):** Identifies non-nominal operational metrics that simulate mechanical load variations. 
- **Hazardous Zone Intrusion (🚷 Geofencing):** Cross references 6 unique machine footprints against pre-defined restricted zones and dynamic personnel worker simulations.
- **Worker Health Emergency (🏥):** Correlates high temperature environment exposure with worker presence models to escalate physical danger alerts. 

### 2. Intelligent & Unified Supervision 
- Simulates FIPA-ACL inter-agent message architectures (`IoT SENSOR_DATA`, `Agent-4 VALIDATION`, `Agent-5 SECURITY`, `Agent-6 RISK_REPORT`) directly traceable in the front-end dashboard UI.
- Synthesizes an actionable 0-100 Global Risk score scaling transparently depending on human presence and machine telemetry context.

### 3. Proactive Rather Than Reactive 
- **Prediction Matrix:** 5-step forecast window predicting system state up to 10 minutes into the future based on trending mathematical bias arrays. 

### 4. Machine Learning Robustness
- **Isolation Forests:** Built-in `scikit-learn` algorithms processing real-time (T=10s) sliding window data vectors in unsupervised configurations to flag anomalies without threshold definitions. 
- **Model Warmups:** Z-Score fallback modes actively supervise telemetry vectors seamlessly while machine learning modules achieve contamination confidence (~25 sample windows).

## API Core

- `ws://localhost:8001/ws/risk`: Live connection for risk snapshots pushing <100ms.
- `http://localhost:8001/api/risk/now`: Quick diagnostic lookup.
- `POST /api/risk/scenario`: System demo injection triggers.

Dependencies: Python 3.9+, scikit-learn, fastapi, websockets.
