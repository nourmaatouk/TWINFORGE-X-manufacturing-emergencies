# 🛡 TWINFORGE-X: AI-Powered Industrial Risk Prevention & Emergency Intelligence
**ARSII Carthage Challenge Submission | Organization: ARSII Carthage**

<p align="center">
  <img src="https://img.shields.io/badge/Status-Functional_Prototype-success?style=for-the-badge" alt="Functional Prototype">
  <img src="https://img.shields.io/badge/AI_Engine-Scikit_Learn_Isolation_Forest-blue?style=for-the-badge" alt="Scikit Learn">
  <img src="https://img.shields.io/badge/Architecture-SMIA_Multi_Agent-orange?style=for-the-badge" alt="SMIA Multi-Agent">
</p>

---

## 🛑 The Challenge

**Industrial facilities operate in complex and high-risk environments.** Safety incidents such as fires, hazardous zone intrusions, and equipment anomalies can rapidly escalate into critical situations. 

According to the ARSII challenge brief, the primary issues with current industrial safety are:
1. **Fragmentation:** Existing safety mechanisms operate independently without effective coordination.
2. **Lack of Situational Awareness:** Operators lack clear, synthesized, and timely information during emergencies.
3. **Reactive Management:** Incidents are detected only *after* they occur, rather than being predicted and prevented.
4. **Harsh Conditions:** Real-time constraints and the need for reliable continuous monitoring make supervision difficult.

**The Objective:** Address the absence of an intelligent and unified safety supervision framework capable of continuously analyzing multiple risk factors in real time and supporting rapid decision-making, while ensuring scalability, reliability, and low-latency operation.

---

## 🚀 The TWINFORGE-X Solution

**TWINFORGE-X** answers the ARSII challenge by transforming an isolated Manufacturing Digital Twin into a **fully coordinated, AI-assisted industrial risk awareness and prevention command center.**

Instead of relying on fragmented, reactive monitoring, we implemented a system that fuses multiple risk vectors into a single, proactive dashboard, powered by unsupervised Machine Learning and Multi-Agent coordination.

### How We Met the Challenge Requirements:

#### 1. Transitioning from "Reactive" to "AI-Assisted & Proactive"
* **The ARSII Need:** Detect incidents *before* they escalate.
* **What We Built:** 
  * **🤖 True AI Detection:** Integrated **Scikit-learn Isolation Forests** to perform real-time multivariate anomaly detection. By analyzing sliding 10-second windows of temperature, vibration, and energy consumption, the system identifies non-linear risks that bypass simple threshold alarms.
  * **📈 Predictive Risk Forecasting:** The risk engine extrapolates current data to predict the hazard severity at T+2, T+4, and T+10 minutes in the future, warning operators preemptively.

#### 2. From "Fragmented" to "Unified & Coordinated"
* **The ARSII Need:** Coordinate independent systems for global situational awareness.
* **What We Built:** 
  * **📡 SMIA Multi-Agent Framework:** We utilized a FIPA-ACL architecture where distinct microservices (IoT Agent, Verification Agent, Security Agent, Risk Agent) constantly communicate. 
  * **Unified Threat Vectors:** The system mathematically fuses physical telemetry (thermal, vibration) with spatial data (geofencing robotic zones, worker presence) to output a single, decisive **0-100 Global Risk Score**.
  * **Transparent Communication Log:** The dashboard visually exposes the real-time agent message flow, proving to operators that the intelligence is coordinated.

#### 3. Scaling for Harsh, Connected & Remote Sites
* **The ARSII Need:** Solutions must consider scalability, reliability, low-latency, and remote deployment.
* **What We Built:**
  * **Low Latency:** Data streams via asynchronous **WebSockets**, enabling sub-100ms UI updates during an emergency.
  * **Reliability:** Built with a Z-score statistical fallback model so the factory remains protected even during the 30-second AI model "warm-up" phase.
  * **Remote Deployment:** Developed using Python FastAPI and containerized architecture, allowing the system to run on local edge servers completely disconnected from the cloud.

---

## 🎬 The Deliverable (Expected Results Met)

As requested by the ARSII prize parameters, this repository contains a complete, functional proof-of-concept:

✅ **Working Prototype:** A fully responsive Vite/React frontend communicating with a Python FastAPI backend. <br>
✅ **AI-Based Detection:** Live, transparent ML Anomaly scores (0-100%) calculated independently per machine.<br>
✅ **System Dashboard:** A dark-mode, high-contrast command center tailored for rapid industrial decision making, featuring automatic Escalation Matrices.<br>
✅ **Video Demonstration Tools:** Built-in scenario injection buttons to instantly simulate complex hazard detection sequences (e.g., Thermal Runaway on CNC-001) for the video recording.

---

## 🛠️ Quick Start Guide

### System Requirements
* Python 3.9+
* Node.js v16+
* `gemini-2.5-flash` API Key (Populated in `.env`)

### 1. Start the Auth Backend (Node.js)
```sh
cd Backend
npm install
npm start
```

### 2. Start the Frontend UI (Vite)
```sh
cd Frontend/vite-project
npm install
npm run dev -- --host
```

### 3. Start the TWINFORGE-X Risk Server (Python)
```sh
cd twinforge/services/Convesation_and_orchestrator_agents
pip install -r requirements.txt
python run.py
```

### 4. Running the Demo Scenario
1. Open up `http://localhost:5173` in a modern browser and sign in.
2. Select the **🛡 Risk Intel** tab on the navigation bar.
3. Observe the "AI Detection Engine" metrics as the Isolation Forests warm up.
4. Click **🔥 Overheat CNC-001** under the Demo Scenarios menu.
5. Watch the ML Anomaly Badge cross the 60% threshold, observe the inter-agent log populate with warnings, and witness the system trigger the **EMERGENCY LOCKDOWN MODE** when the Global Risk Score exceeds 85.
6. Click **✅ Clear / Reset** to demonstrate the system's rapid recovery tracking.

---
**Prepared specifically for the ARSII Carthage Hackathon.**
`<carthage@arsii.org>`
