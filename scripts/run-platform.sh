#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-docker}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

ensure_env_file() {
  if [[ ! -f "$ROOT_DIR/.env.microservices" ]]; then
    cp "$ROOT_DIR/.env.microservices.example" "$ROOT_DIR/.env.microservices"
    echo "Created .env.microservices from example. Update values before production use."
  fi
}

case "$MODE" in
  local)
    (cd "$ROOT_DIR/Backend" && npm install && npm run start) &
    (cd "$ROOT_DIR/Frontend/vite-project" && npm install && npm run dev -- --host 0.0.0.0 --port 18080) &
    (cd "$ROOT_DIR/twinforge/services/Convesation_and_orchestrator_agents" && python -m pip install -r requirements.txt && python run.py) &
    wait
    ;;
  docker)
    ensure_env_file
    cd "$ROOT_DIR"
    docker compose --env-file .env.microservices -f docker-compose.microservices.yml up -d --build
    ;;
  docker-cloudflare)
    ensure_env_file
    cd "$ROOT_DIR"
    docker compose --env-file .env.microservices -f docker-compose.microservices.yml --profile cloudflare up -d --build
    ;;
  stop)
    cd "$ROOT_DIR"
    docker compose --env-file .env.microservices -f docker-compose.microservices.yml down
    ;;
  *)
    echo "Usage: $0 [local|docker|docker-cloudflare|stop]"
    exit 1
    ;;
esac
