# API Reference

## Agent Endpoints

All agents expose:
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /process` - Process a request

## Ports
| Service | Port |
|---------|------|
| langgraph-orchestrator | 8000 |
| agent-conversation | 8001 |
| agent-orchestrator | 8002 |
| agent-data-iot | 8003 |
| agent-verifier | 8004 |
| agent-security | 8005 |
| mcp-mock-server | 9001 |
| Grafana | 3000 |
| Jaeger | 16686 |
| Prometheus | 9090 |
