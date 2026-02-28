# TWINFORGE-X: Comprehensive Documentation

Welcome to the definitive manual for **TWINFORGE-X**, the AI-Powered Industrial Risk Prevention & Emergency Intelligence platform developed for the ARSII Carthage Hackathon.

Below you will find a full description of the project, the underlying SMIA multi-agent pipeline, the tech stack, our agent roadmap, and exact step-by-step instructions to boot the system.

---

## 📖 1. Project Overview

At its core, **TWINFORGE-X** is an advanced Manufacturing Digital Twin that has been upgraded into a cohesive, intelligent safety and risk management supervisor. 

Industrial facilities produce massive amounts of sensor data across hundreds of machines, but that telemetry is often siloed. Safety systems remain reactive—sounding an alarm only when a machine has already overheated or a zone has already been breached.

TWINFORGE-X solves this by using a **Multi-Agent Architecture** to constantly monitor, verify, and mathematically fuse data (temperature, vibration, worker locations). It passes this fused data into an unsupervised Machine Learning engine (Isolation Forest) to detect complex anomalies *before* they trip simple threshold alarms. 

The resulting "Global Risk Score" is displayed on a real-time, low-latency React dashboard featuring custom escalation matrices and automated lockdown protocols.

---

## 🏗️ 2. What the Project Contains

The repository is modularized into three main components:

1. **`Backend/` (Auth & Security API)**
   - A Node.js / Express microservice handling user authentication, secure JWT issuance, and API routing.
   
2. **`twinforge/` (The Core Engine)**
   - A Python / FastAPI backend that houses the actual Digital Twin state, the Agent Simulator, the Scikit-learn Risk Engine, and the high-speed WebSocket controllers.
   
3. **`Frontend/vite-project/` (The Command Center UI)**
   - A React / Vite application that consumes the WebSockets and APIs to power the dark-mode dashboard. Includes full 3D rendering of the factory floor, a natural language Chat Agent, and the Risk Intelligence overlay.

---

## ⚙️ 3. The SMIA Multi-Agent Pipeline

To prevent data silos, the system is designed around the **SMIA (Smart Manufacturing Intelligent Agents)** methodology. The pipeline operates sequentially and continuously:

1. **Agent 3 (IoT Telemetry):** Generates and ingests raw mathematical streams (sine waves mimicking temperature, vibration, energy) mimicking live physical assets on the factory floor.
2. **Agent 4 (Data Verifier):** Cross-checks incoming telemetry packets for integrity and formats them into a standardized vector.
3. **Agent 5 (Security & Context):** Adds real-world context to the data vector, checking geofencing parameters (e.g., "Are workers currently present in the restriction zone around this machine?").
4. **Agent 6 (Risk Fusion Engine):** 
   - Receives the fully contextualized vector.
   - Feeds it into a **Scikit-learn Isolation Forest** model (looking for non-linear, multidimensional anomalies).
   - Feeds it concurrently into a classical **Z-Score Statistical Array**.
   - Fuses these into a `0-100` Anomaly Score per machine.
5. **Orchestrator Agent:** Aggregates the individual anomaly scores into a `Global Risk Score`. If the score breaches a critical threshold (≥85), it broadcasts an Emergency Lockdown signal via WebSocket directly to the Dashboard.

---

## 🚀 4. Agent Roadmap

While TWINFORGE-X currently utilizes a robust 6-Agent pipeline, our roadmap for scaling the system includes:

- **Phase 1 (Current):** Descriptive and Predictive Analytics using Isolation Forests and Time-Series Forecasting (TFT) on simulated telemetry.
- **Phase 2 (Integration):** Replacing Agent 3's simulator with real MQTT or OPC-UA bindings to connect directly to physical Siemens/Allen-Bradley PLCs.
- **Phase 3 (Prescriptive Generation):** Upgrading the LLM capabilities (currently Gemini 2.5) to not just answer questions about the factory, but to autonomously generate PyTorch repair scripts and write them to the maintenance queue when an anomaly is detected.
- **Phase 4 (Swarm Deployment):** Deploying the agents via Kubernetes across multiple edge-devices on the factory floor, allowing the system to operate via localized mesh-networking if the primary server goes offline.

---

## 💻 5. Technologies Used

* **Frontend:** React, Vite, Vanilla CSS, WebSockets, Three.js (for the 3D Twin map).
* **AI & Data Science:** Scikit-learn (Isolation Forests), NumPy, Math, and Google Gemini API (for NLP).
* **Backend:** Python 3.9+, FastAPI, Uvicorn, Pydantic.
* **Auth Service:** Node.js, Express, JWT, dotenv.
* **Architecture Design:** FIPA-ACL (Agent Communication Language), SMIA specs, Microservices.

---

## ⚡ 6. Exact Steps to Run the Code

To run the entire suite locally for a demonstration, you must start the three core microservices in three **separate terminal windows**.

### Prerequisites
- Python 3.9+ installed
- Node.js (v16+) installed
- A valid Gemini API key inside `twinforge/services/Convesation_and_orchestrator_agents/.env` and `Backend/.env`

### Terminal 1: Start the Auth Backend
Provides login routing and JWT issuance.
```sh
cd Backend
npm install
node -r dotenv/config server.js
```
*(Runs on port 5000)*

### Terminal 2: Start the Risk Engine & Fast API Server
Powers the AI models, WebSockets, and digital twin simulation.
```sh
cd twinforge/services/Convesation_and_orchestrator_agents
pip install -r requirements.txt
python run.py
```
*(Runs on ports 8001 and 8002)*

### Terminal 3: Start the UI Dashboard
Powers the visualization interface.
```sh
cd Frontend/vite-project
npm install
npm run dev -- --host
```
*(Runs on port 5173)*

### Launching the Demo Experience
1. Navigate to `http://localhost:5173` in your browser.
2. Sign in using any dummy credentials (or click Create Account).
3. Click on the **🛡 Risk Intel** tab on the side navigation bar.
4. Interact with the **Demo Scenarios** panel on the top right to instantly inject thermal runaway or zone intrusion algorithms into the simulation and watch the AI react!
