# TWINFORGE-X Frontend Shell (React/Vite)

This is the central entry point and UI orchestrator for **TWINFORGE-X** — the AI-Powered Industrial Risk Prevention & Emergency Intelligence dashboard, built for the ARSII Challenge.

## Layout & Design Architecture

The UI seamlessly integrates the overarching React-based authentication application mapping users directly into the specific module views utilizing iframe and direct-port injections at:
- `localhost:8001/` (The actual TwinForge Risk Engine Interface).

### Core Features

- Modern UI built with Vite and React for high-performance reloading.
- Auth protected routing ensuring only verified administrators access the risk control panels.
- Deep linking support (e.g. `http://localhost:5173/?next=/risk`) allowing direct access to the `Risk Intel` tabs post-login.

### Requirements

```sh
Node.js >= 16
```

### Installation

```sh
cd Frontend/vite-project
npm install
npm run dev -- --host
```

The system will build and hot-reload. Navigate to `http://localhost:5173` to interact with the TWINFORGE-X experience. Ensure the Python engine is running on `:8001` and the Node.js auth backend on `:5000` to prevent network timeouts.

## ARSII Challenge Context

This interface directly delivers the "Unified Framework" portion of the ARSII challenge prompt. It brings an otherwise fragmented array of IoT telemetry data into an AI-driven, centrally coordinated dashboard, translating Isolation Forest mathematics into readable, color-coded emergency prompts for rapid operator action.
