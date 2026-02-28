#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# TWINFORGE — Deploy to Azure Container Apps (Bash)
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
export AZURE_CORE_ONLY_SHOW_ERRORS=True

# ── Defaults ──────────────────────────────────────────────────────────────
RG="${AZURE_RESOURCE_GROUP:-twinforge-rg}"
LOCATION="${AZURE_LOCATION:-eastus}"
ACR_NAME="${AZURE_ACR_NAME:-twinforgeacr}"
ENV_NAME="${AZURE_CONTAINER_APP_ENV:-twinforge-env}"

# ── Parse args ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --rg)        RG="$2";       shift 2 ;;
    --location)  LOCATION="$2"; shift 2 ;;
    --acr)       ACR_NAME="$2"; shift 2 ;;
    --env)       ENV_NAME="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

# ── Generate secrets ─────────────────────────────────────────────────────
: "${MESSAGE_SIGNING_KEY:=$(openssl rand -hex 32)}"
: "${REDIS_PASSWORD:=$(openssl rand -hex 16)}"
export MESSAGE_SIGNING_KEY REDIS_PASSWORD

# ── Load Backend/.env ────────────────────────────────────────────────────
if [[ -f Backend/.env ]]; then
  set -a
  source Backend/.env
  set +a
  echo "[INFO] Loaded Backend/.env"
fi

ACR_SERVER="${ACR_NAME}.azurecr.io"

echo ""
echo "========================================================"
echo "   TWINFORGE — Azure Container Apps Deployment"
echo "========================================================"
echo ""
echo "  Resource Group : $RG"
echo "  Location       : $LOCATION"
echo "  ACR            : $ACR_SERVER"
echo "  Environment    : $ENV_NAME"
echo ""

# ══════════════════════════════════════════════════════════════════════════
# STEP 1 — Resource Group
# ══════════════════════════════════════════════════════════════════════════
echo "[1/9] Creating resource group..."
az group create --name "$RG" --location "$LOCATION" --output none
echo "  [OK] Resource group '$RG'"

# ══════════════════════════════════════════════════════════════════════════
# STEP 2 — Azure Container Registry
# ══════════════════════════════════════════════════════════════════════════
echo "[2/9] Creating Azure Container Registry..."
az acr create --name "$ACR_NAME" --resource-group "$RG" --sku Basic --admin-enabled true --output none
az acr login --name "$ACR_NAME"
echo "  [OK] ACR '$ACR_SERVER'"

# ══════════════════════════════════════════════════════════════════════════
# STEP 3 — Build & Push Docker Images
# ══════════════════════════════════════════════════════════════════════════
echo "[3/9] Building and pushing Docker images..."

build_and_push() {
  local name=$1 context=$2 dockerfile=$3
  shift 3
  local tag="${ACR_SERVER}/${name}:latest"
  local build_args=""
  for arg in "$@"; do build_args="$build_args --build-arg $arg"; done

  echo "  Building $name..."
  docker build -t "$tag" -f "${context}/${dockerfile}" $build_args "$context"
  echo "  Pushing $name..."
  docker push "$tag"
}

build_and_push auth-backend        Backend                                                Dockerfile
build_and_push auth-frontend       Frontend/vite-project                                  Dockerfile NGINX_CONF=azure.conf VITE_API_URL=/api
build_and_push twinforge-dashboard "twinforge/services/Convesation_and_orchestrator_agents" Dockerfile
build_and_push agent-data-iot      twinforge/services/agent-data-iot                      Dockerfile
build_and_push agent-verifier      twinforge/services/agent-verifier                      Dockerfile
build_and_push agent-security      twinforge/services/agent-security                      Dockerfile
build_and_push mcp-mock-server     twinforge/services/mcp-mock-server                     Dockerfile
build_and_push dataset-replay      twinforge/services/dataset-replay                      Dockerfile
build_and_push mosquitto           deploy/azure/mosquitto                                 Dockerfile

echo "  [OK] All 9 images pushed to ACR"

# ══════════════════════════════════════════════════════════════════════════
# STEP 4 — Container Apps Environment
# ══════════════════════════════════════════════════════════════════════════
echo "[4/9] Creating Container Apps environment..."
az containerapp env create \
    --name "$ENV_NAME" \
    --resource-group "$RG" \
    --location "$LOCATION" \
    --output none
echo "  [OK] Environment '$ENV_NAME'"

# ══════════════════════════════════════════════════════════════════════════
# STEP 5 — Get ACR Credentials
# ══════════════════════════════════════════════════════════════════════════
echo "[5/9] Retrieving ACR credentials..."
ACR_USER=$(az acr credential show --name "$ACR_NAME" --query "username" -o tsv)
ACR_PASS=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)
echo "  [OK] Credentials retrieved"

# ══════════════════════════════════════════════════════════════════════════
# STEP 6 — Deploy Infrastructure (Redis + Mosquitto)
# ══════════════════════════════════════════════════════════════════════════
echo "[6/9] Deploying infrastructure..."

echo "  Deploying Redis..."
az containerapp create \
    --name redis \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "redis:7-alpine" \
    --args "redis-server" "--requirepass" "$REDIS_PASSWORD" \
    --target-port 6379 \
    --transport tcp \
    --exposed-port 6379 \
    --ingress internal \
    --min-replicas 1 --max-replicas 1 \
    --cpu 0.25 --memory 0.5Gi \
    --output none

echo "  Deploying Mosquitto..."
az containerapp create \
    --name mosquitto \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/mosquitto:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 1883 \
    --transport tcp \
    --exposed-port 1883 \
    --ingress internal \
    --min-replicas 1 --max-replicas 1 \
    --cpu 0.25 --memory 0.5Gi \
    --output none

echo "  [OK] Redis + Mosquitto deployed"

# ══════════════════════════════════════════════════════════════════════════
# STEP 7 — Deploy Application Services
# ══════════════════════════════════════════════════════════════════════════
echo "[7/9] Deploying application services..."

REDIS_URL="redis://:${REDIS_PASSWORD}@redis:6379"

echo "  Deploying auth-backend..."
az containerapp create \
    --name auth-backend \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/auth-backend:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 5000 \
    --ingress internal \
    --min-replicas 1 --max-replicas 3 \
    --cpu 0.5 --memory 1.0Gi \
    --env-vars \
        "NODE_ENV=production" \
        "AUTH_DB_PATH=/data/auth.db" \
        "JWT_SECRET=${JWT_SECRET}" \
        "OTP_SECRET=${OTP_SECRET}" \
        "DATA_ENCRYPTION_KEYS=${DATA_ENCRYPTION_KEYS}" \
        "ACTIVE_ENCRYPTION_KEY_ID=${ACTIVE_ENCRYPTION_KEY_ID}" \
        "RESEND_API_KEY=${RESEND_API_KEY}" \
        "RESEND_FROM=${RESEND_FROM}" \
        "LOGIN_EMAIL=${LOGIN_EMAIL}" \
        "LOGIN_PASSWORD=${LOGIN_PASSWORD}" \
        "TRUST_PROXY=1" \
        "APP_ORIGIN=https://PLACEHOLDER" \
        "APP_ORIGINS=https://PLACEHOLDER" \
        "DASHBOARD_URL=https://PLACEHOLDER/dashboard/" \
    --output none
# If the app already exists in other workflows, ensure latest image is applied.
az containerapp update \
    --name auth-backend \
    --resource-group "$RG" \
    --image "${ACR_SERVER}/auth-backend:latest" \
    --output none
az containerapp ingress update \
    --name auth-backend \
    --resource-group "$RG" \
    --type internal \
    --target-port 5000 \
    --transport auto \
    --allow-insecure true \
    --output none

echo "  Deploying twinforge-dashboard..."
az containerapp create \
    --name twinforge-dashboard \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/twinforge-dashboard:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 8001 \
    --ingress internal \
    --min-replicas 1 --max-replicas 3 \
    --cpu 0.5 --memory 1.0Gi \
    --env-vars \
        "AUTH_BACKEND_URL=http://auth-backend" \
        "AUTH_LOGIN_URL=https://PLACEHOLDER" \
        "REDIS_URL=${REDIS_URL}" \
        "MESSAGE_SIGNING_KEY=${MESSAGE_SIGNING_KEY}" \
    --output none
az containerapp ingress update \
    --name twinforge-dashboard \
    --resource-group "$RG" \
    --type internal \
    --target-port 8001 \
    --transport auto \
    --allow-insecure true \
    --output none

echo "  Deploying agent-data-iot..."
az containerapp create \
    --name agent-data-iot \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/agent-data-iot:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 8003 \
    --ingress internal \
    --min-replicas 1 --max-replicas 3 \
    --cpu 0.5 --memory 1.0Gi \
    --env-vars \
        "REDIS_URL=${REDIS_URL}" \
        "MESSAGE_SIGNING_KEY=${MESSAGE_SIGNING_KEY}" \
        "MQTT_BROKER_HOST=mosquitto" \
        "MQTT_BROKER_PORT=1883" \
        "SECURITY_AGENT_URL=http://agent-security" \
        "AGENT_ID=agent_3" \
        "SERVICE_PORT=8003" \
        "LOG_LEVEL=INFO" \
    --output none

echo "  Deploying agent-verifier..."
az containerapp create \
    --name agent-verifier \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/agent-verifier:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 8004 \
    --ingress internal \
    --min-replicas 1 --max-replicas 3 \
    --cpu 0.5 --memory 1.0Gi \
    --env-vars \
        "REDIS_URL=${REDIS_URL}" \
        "MESSAGE_SIGNING_KEY=${MESSAGE_SIGNING_KEY}" \
        "SECURITY_AGENT_URL=http://agent-security" \
        "AGENT_ID=agent_4" \
        "PORT=8004" \
    --output none

echo "  Deploying agent-security..."
az containerapp create \
    --name agent-security \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/agent-security:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 8005 \
    --ingress internal \
    --min-replicas 1 --max-replicas 3 \
    --cpu 0.5 --memory 1.0Gi \
    --env-vars \
        "REDIS_URL=${REDIS_URL}" \
        "MESSAGE_SIGNING_KEY=${MESSAGE_SIGNING_KEY}" \
        "AGENT_ID=agent_5" \
        "PORT=8005" \
        "LOCKDOWN_ENABLED=true" \
        "ALLOWED_IPS=0.0.0.0/0,::0/0" \
        "AGENT_URLS=agent_1=http://twinforge-dashboard,agent_2=http://twinforge-dashboard,agent_3=http://agent-data-iot,agent_4=http://agent-verifier" \
    --output none

echo "  Deploying mcp-mock-server..."
az containerapp create \
    --name mcp-mock-server \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/mcp-mock-server:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 9001 \
    --ingress internal \
    --min-replicas 1 --max-replicas 1 \
    --cpu 0.25 --memory 0.5Gi \
    --output none

echo "  Deploying dataset-replay..."
az containerapp create \
    --name dataset-replay \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/dataset-replay:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --min-replicas 1 --max-replicas 1 \
    --cpu 0.25 --memory 0.5Gi \
    --env-vars \
        "AGENT_DATA_IOT_URL=http://agent-data-iot" \
        "REPLAY_SPEED=1.0" \
        "REPLAY_INTERVAL_SEC=2.0" \
        "BATCH_SIZE=5" \
    --output none

echo "  [OK] All services deployed"

# ══════════════════════════════════════════════════════════════════════════
# STEP 8 — Deploy Frontend (External Ingress)
# ══════════════════════════════════════════════════════════════════════════
echo "[8/9] Deploying auth-frontend (public)..."
AUTH_BACKEND_HOST=auth-backend
DASHBOARD_HOST=twinforge-dashboard

az containerapp create \
    --name auth-frontend \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "${ACR_SERVER}/auth-frontend:latest" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 80 \
    --ingress external \
    --min-replicas 1 --max-replicas 5 \
    --cpu 0.25 --memory 0.5Gi \
    --env-vars \
        "AUTH_BACKEND_HOST=${AUTH_BACKEND_HOST}" \
        "DASHBOARD_HOST=${DASHBOARD_HOST}" \
    --output none
# If the app already exists in other workflows, ensure latest image is applied.
az containerapp update \
    --name auth-frontend \
    --resource-group "$RG" \
    --image "${ACR_SERVER}/auth-frontend:latest" \
    --set-env-vars \
        "AUTH_BACKEND_HOST=${AUTH_BACKEND_HOST}" \
        "DASHBOARD_HOST=${DASHBOARD_HOST}" \
    --output none
echo "  [OK] Frontend deployed with external ingress"

# ══════════════════════════════════════════════════════════════════════════
# STEP 9 — Get Public URL & Update Services
# ══════════════════════════════════════════════════════════════════════════
echo "[9/9] Configuring public URLs..."
FQDN=$(az containerapp show --name auth-frontend --resource-group "$RG" --query "properties.configuration.ingress.fqdn" -o tsv)
PUBLIC_URL="https://${FQDN}"

az containerapp update \
    --name auth-backend \
    --resource-group "$RG" \
    --set-env-vars "APP_ORIGIN=${PUBLIC_URL}" "APP_ORIGINS=${PUBLIC_URL}" "DASHBOARD_URL=${PUBLIC_URL}/dashboard/" \
    --output none

az containerapp update \
    --name twinforge-dashboard \
    --resource-group "$RG" \
    --set-env-vars "AUTH_LOGIN_URL=${PUBLIC_URL}" \
    --output none

HEALTH_URL="${PUBLIC_URL}/api/health"
HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${HEALTH_URL}" || true)
if [[ "$HEALTH_CODE" != "200" ]]; then
  echo "  [WARN] Public auth API probe failed at ${HEALTH_URL} (status: ${HEALTH_CODE:-unreachable})"
else
  echo "  [OK] Public auth API reachable at ${HEALTH_URL}"
fi

echo "  [OK] Public URLs configured"

# ══════════════════════════════════════════════════════════════════════════
# DONE
# ══════════════════════════════════════════════════════════════════════════
echo ""
echo "========================================================"
echo "            DEPLOYMENT COMPLETE"
echo "========================================================"
echo ""
echo "  Application : ${PUBLIC_URL}"
echo "  Dashboard   : ${PUBLIC_URL}/dashboard/"
echo ""
echo "  SAVE THESE SECRETS:"
echo "    MESSAGE_SIGNING_KEY = ${MESSAGE_SIGNING_KEY}"
echo "    REDIS_PASSWORD      = ${REDIS_PASSWORD}"
echo ""
