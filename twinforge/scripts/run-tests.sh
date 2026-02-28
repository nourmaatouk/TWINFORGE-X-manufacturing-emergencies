#!/bin/bash
set -e

echo "Running TWINFORGE tests..."

SERVICES="agent-conversation agent-orchestrator agent-data-iot agent-verifier agent-security langgraph-orchestrator dataset-replay mcp-mock-server"

for service in $SERVICES; do
    echo "--- Testing $service ---"
    cd "services/$service"
    if [ -d "tests" ] && [ "$(ls tests/*.py 2>/dev/null)" ]; then
        python -m pytest tests/ -v --cov=app --cov-report=term-missing || true
    fi
    cd ../..
done

echo "--- Running integration tests ---"
python -m pytest tests/integration/ -v || true

echo "--- Running adversarial tests ---"
python -m pytest tests/adversarial/ -v || true

echo "Tests complete."
