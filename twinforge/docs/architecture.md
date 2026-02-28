# Architecture

## Overview
TWINFORGE is a microservices-based manufacturing digital twin platform with 5 specialized AI agents.

## Agents
- **Agent 1 (Conversation)**: Planner - user interaction, intent classification
- **Agent 2 (Orchestrator)**: Executor - AAS creation, KPI computation, RAG retrieval
- **Agent 3 (Data IoT)**: Executor - OPC-UA, MQTT, MCP data collection
- **Agent 4 (Verifier)**: Critic - validates outputs, detects anomalies
- **Agent 5 (Security)**: Guardian - real-time threat detection and monitoring

## Communication
All inter-agent communication flows through Redis pub/sub with HMAC-SHA256 signed messages.

## Data Stores
- **PostgreSQL + pgvector**: AAS registry, RAG knowledge base
- **InfluxDB**: Time-series sensor data
- **Redis**: Message bus, caching
- **Vault**: Secrets management
