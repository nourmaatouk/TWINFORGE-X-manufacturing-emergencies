# Microservice Runbook

## Files created/updated for Docker microservice architecture

- `docker-compose.microservices.yml`
- `Backend/Dockerfile`
- `Backend/.dockerignore`
- `Frontend/vite-project/Dockerfile`
- `Frontend/vite-project/nginx/default.conf`
- `Frontend/vite-project/.dockerignore`
- `twinforge/services/Convesation_and_orchestrator_agents/Dockerfile`
- `twinforge/services/Convesation_and_orchestrator_agents/.dockerignore`
- `scripts/run-platform.ps1`
- `scripts/run-platform.sh`
- `scripts/run-local.ps1`
- `scripts/run-docker.ps1`
- `.env.microservices`
- `.env.microservices.example`
- `deploy/cloudflare/README.md`
- `deploy/cloudflare/tunnel-config.example.yml`

## Start commands

### Docker mode

```powershell
./scripts/run-docker.ps1
```

- Frontend URL: `http://localhost:18080`
- Dashboard URL: `http://localhost:18080/dashboard`

### Local mode

```powershell
./scripts/run-local.ps1
```

- Frontend dev URL: `http://localhost:18080`
- Backend URL: `http://localhost:5000`
- Dashboard URL: `http://localhost:8001`

## Rebuild after code or env changes

### If you changed code or Dockerfiles

```powershell
docker compose --env-file .env.microservices -f docker-compose.microservices.yml up -d --build
```

### If you changed only env values

```powershell
docker compose --env-file .env.microservices -f docker-compose.microservices.yml down
docker compose --env-file .env.microservices -f docker-compose.microservices.yml up -d --force-recreate
```

### Full clean rebuild (if something is cached wrong)

```powershell
docker compose --env-file .env.microservices -f docker-compose.microservices.yml down --remove-orphans
docker compose --env-file .env.microservices -f docker-compose.microservices.yml build --no-cache
docker compose --env-file .env.microservices -f docker-compose.microservices.yml up -d
```
