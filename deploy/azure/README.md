# Azure Deployment Guide — TWINFORGE

Deploy the complete TWINFORGE multi-agent platform (10 services) to **Azure Container Apps**.

## Architecture on Azure

```
                    ┌──────────────────────────────────────────────────┐
                    │         Azure Container Apps Environment          │
                    │                                                  │
 Internet ────────► │  ┌───────────────┐                               │
     HTTPS          │  │ auth-frontend │  (external ingress, port 80)  │
                    │  │   Nginx SPA   │                               │
                    │  └──┬────┬───────┘                               │
                    │     │    │                                        │
                    │     │    │  ┌──────────────────┐                  │
                    │     │    └─►│ twinforge-dashboard│ Agent 1+2      │
                    │     │      │ (internal, 8001)   │                 │
                    │     │      └──────────────────┘                  │
                    │     │                                            │
                    │     │  ┌────────────────┐                        │
                    │     └─►│  auth-backend  │ Node.js Express        │
                    │        │ (internal, 5000)│                        │
                    │        └────────────────┘                        │
                    │                                                  │
                    │  ┌─────────────┐ ┌──────────────┐ ┌────────────┐│
                    │  │agent-data-iot│ │agent-verifier│ │agent-secur.││
                    │  │(internal)    │ │(internal)    │ │(internal)  ││
                    │  │  8003       │ │  8004        │ │  8005      ││
                    │  └─────────────┘ └──────────────┘ └────────────┘│
                    │                                                  │
                    │  ┌──────────┐ ┌───────────┐ ┌─────────────────┐ │
                    │  │  Redis   │ │ Mosquitto │ │  mcp-mock-server│ │
                    │  │TCP:6379  │ │ TCP:1883  │ │  HTTP:9001      │ │
                    │  └──────────┘ └───────────┘ └─────────────────┘ │
                    │                                                  │
                    │  ┌─────────────────┐                             │
                    │  │  dataset-replay │ (no ingress, background)    │
                    │  └─────────────────┘                             │
                    └──────────────────────────────────────────────────┘
```

## Prerequisites

| Requirement | Version | Install |
|---|---|---|
| Azure CLI | >= 2.53 | [Install Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) |
| Docker Desktop | >= 24.0 | [Install Docker](https://docs.docker.com/get-docker/) |
| Azure subscription | — | [Free account](https://azure.microsoft.com/free/) with Contributor access |

## Quick Deploy (automated)

### Windows (PowerShell)

```powershell
# 1. Login to Azure
az login

# 2. Run deploy script (uses defaults: eastus, twinforge-rg, twinforgeacr)
.\deploy\azure\deploy-azure.ps1

# Or customize:
.\deploy\azure\deploy-azure.ps1 -AcrName "myuniqueacr2026" -Location "westeurope"
```

### Linux / macOS (Bash)

```bash
# 1. Login to Azure
az login

# 2. Run deploy script
chmod +x deploy/azure/deploy-azure.sh
./deploy/azure/deploy-azure.sh

# Or customize:
./deploy/azure/deploy-azure.sh --acr myuniqueacr2026 --location westeurope
```

The script automatically:
1. Creates a Resource Group
2. Creates an Azure Container Registry (ACR)
3. Builds all 9 Docker images locally and pushes to ACR
4. Creates a Container Apps Environment
5. Deploys Redis (TCP) and Mosquitto (TCP) as internal services
6. Deploys all 8 application containers with correct environment variables
7. Deploys `auth-frontend` with external HTTPS ingress
8. Retrieves the public FQDN and updates `auth-backend` and `twinforge-dashboard` with the correct URLs

## Manual Step-by-Step Deployment

If you prefer to deploy manually or need more control:

### Step 1 — Login & set subscription

```bash
az login
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"
```

### Step 2 — Create Resource Group

```bash
az group create --name twinforge-rg --location eastus
```

### Step 3 — Create Azure Container Registry

```bash
# Name must be globally unique, lowercase, 5-50 characters
az acr create --name twinforgeacr --resource-group twinforge-rg \
    --sku Basic --admin-enabled true

az acr login --name twinforgeacr
```

### Step 4 — Build and push Docker images

```bash
ACR=twinforgeacr.azurecr.io

# Auth backend
docker build -t $ACR/auth-backend:latest Backend/
docker push $ACR/auth-backend:latest

# Auth frontend (with Azure nginx config)
docker build -t $ACR/auth-frontend:latest \
    --build-arg NGINX_CONF=azure.conf \
    --build-arg VITE_API_URL=/api \
    Frontend/vite-project/
docker push $ACR/auth-frontend:latest

# Dashboard (Agent 1 + 2)
docker build -t $ACR/twinforge-dashboard:latest \
    twinforge/services/Convesation_and_orchestrator_agents/
docker push $ACR/twinforge-dashboard:latest

# Agent 3 — Data/IoT
docker build -t $ACR/agent-data-iot:latest twinforge/services/agent-data-iot/
docker push $ACR/agent-data-iot:latest

# Agent 4 — Verifier
docker build -t $ACR/agent-verifier:latest twinforge/services/agent-verifier/
docker push $ACR/agent-verifier:latest

# Agent 5 — Security
docker build -t $ACR/agent-security:latest twinforge/services/agent-security/
docker push $ACR/agent-security:latest

# MCP Mock Server
docker build -t $ACR/mcp-mock-server:latest twinforge/services/mcp-mock-server/
docker push $ACR/mcp-mock-server:latest

# Dataset Replay
docker build -t $ACR/dataset-replay:latest twinforge/services/dataset-replay/
docker push $ACR/dataset-replay:latest

# Mosquitto (with baked-in config)
docker build -t $ACR/mosquitto:latest deploy/azure/mosquitto/
docker push $ACR/mosquitto:latest
```

### Step 5 — Create Container Apps Environment

```bash
az containerapp env create \
    --name twinforge-env \
    --resource-group twinforge-rg \
    --location eastus
```

### Step 6 — Get ACR credentials

```bash
ACR_USER=$(az acr credential show --name twinforgeacr --query "username" -o tsv)
ACR_PASS=$(az acr credential show --name twinforgeacr --query "passwords[0].value" -o tsv)
```

### Step 7 — Generate secrets

```bash
MESSAGE_SIGNING_KEY=$(openssl rand -hex 32)
REDIS_PASSWORD=$(openssl rand -hex 16)
REDIS_URL="redis://:${REDIS_PASSWORD}@redis:6379"
echo "MESSAGE_SIGNING_KEY=$MESSAGE_SIGNING_KEY"
echo "REDIS_PASSWORD=$REDIS_PASSWORD"
```

### Step 8 — Deploy infrastructure

```bash
# Redis
az containerapp create --name redis \
    --resource-group twinforge-rg --environment twinforge-env \
    --image redis:7-alpine \
    --args "redis-server" "--requirepass" "$REDIS_PASSWORD" \
    --target-port 6379 --transport tcp --exposed-port 6379 \
    --ingress internal --min-replicas 1 --max-replicas 1 \
    --cpu 0.25 --memory 0.5Gi

# Mosquitto
az containerapp create --name mosquitto \
    --resource-group twinforge-rg --environment twinforge-env \
    --image $ACR/mosquitto:latest \
    --registry-server $ACR --registry-username $ACR_USER --registry-password $ACR_PASS \
    --target-port 1883 --transport tcp --exposed-port 1883 \
    --ingress internal --min-replicas 1 --max-replicas 1 \
    --cpu 0.25 --memory 0.5Gi
```

### Step 9 — Deploy application services

Deploy each service with `az containerapp create`. See `deploy-azure.ps1` for the full set of commands with all environment variables.

Key points for each service:
- **Internal HTTP services** use `--ingress internal` (no port number in URLs between services)
- **TCP services** (Redis, Mosquitto) use `--transport tcp --exposed-port <port>`
- **`auth-frontend`** is the ONLY service with `--ingress external`
- **`dataset-replay`** has no ingress (background worker)

### Step 10 — Get public URL and update services

```bash
FQDN=$(az containerapp show --name auth-frontend --resource-group twinforge-rg \
    --query "properties.configuration.ingress.fqdn" -o tsv)
PUBLIC_URL="https://$FQDN"

# Update auth-backend with real URLs
az containerapp update --name auth-backend --resource-group twinforge-rg \
    --set-env-vars "APP_ORIGIN=$PUBLIC_URL" "APP_ORIGINS=$PUBLIC_URL" \
    "DASHBOARD_URL=$PUBLIC_URL/dashboard/"

# Update dashboard with login redirect URL
az containerapp update --name twinforge-dashboard --resource-group twinforge-rg \
    --set-env-vars "AUTH_LOGIN_URL=$PUBLIC_URL"

echo "Application live at: $PUBLIC_URL"
```

## Post-Deployment

### Verify services

```bash
# List all container apps
az containerapp list --resource-group twinforge-rg -o table

# Check logs for a specific service
az containerapp logs show --name auth-backend --resource-group twinforge-rg --follow

# Check revisions
az containerapp revision list --name auth-backend --resource-group twinforge-rg -o table
```

### Update a service

```bash
# Rebuild and push the updated image
docker build -t twinforgeacr.azurecr.io/auth-backend:latest Backend/
docker push twinforgeacr.azurecr.io/auth-backend:latest

# Update the container app to pull the new image
az containerapp update --name auth-backend --resource-group twinforge-rg \
    --image twinforgeacr.azurecr.io/auth-backend:latest
```

### Tear down

```bash
# Delete everything
az group delete --name twinforge-rg --yes --no-wait
```

## Security Notes

- Only `auth-frontend` has external (public) ingress — all other services are internal-only
- Redis uses password authentication
- All inter-agent messages are HMAC-SHA256 signed via `MESSAGE_SIGNING_KEY`
- For production: store secrets in **Azure Key Vault** and use **Managed Identity** for ACR access
- auth-backend uses in-container SQLite; for production persistence, mount **Azure Files** or migrate to **Azure SQL**

## Estimated Cost

| Component | SKU | Monthly Cost |
|---|---|---|
| Container Apps (10 services) | Consumption plan | ~$30-80 |
| Container Registry | Basic | ~$5 |
| **Total** | | **~$35-85/month** |

*Costs vary by usage. First 2M requests/month and 180,000 vCPU-seconds are free.*
