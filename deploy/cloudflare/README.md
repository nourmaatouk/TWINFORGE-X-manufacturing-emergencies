# Cloudflare Deployment (Tunnel)

## 1) Create tunnel and DNS routes

Run these on a machine authenticated to Cloudflare:

```bash
cloudflared tunnel login
cloudflared tunnel create twinforge-platform
cloudflared tunnel route dns twinforge-platform auth.your-domain.com
cloudflared tunnel route dns twinforge-platform dashboard.your-domain.com
```

## 2) Configure tunnel

- Copy `deploy/cloudflare/tunnel-config.example.yml` to a real config file.
- Replace tunnel UUID and hostnames.

## 3) Set runtime env file

- Copy `.env.microservices.example` to `.env.microservices`.
- Set `CLOUDFLARE_TUNNEL_TOKEN` from your Cloudflare tunnel.
- Set `AUTH_LOGIN_URL`, `VITE_DASHBOARD_URL`, `APP_ORIGIN`, and `APP_ORIGINS` to your production URLs.

Local Docker default URLs are:
- `http://localhost:18080` for login frontend
- `http://localhost:18080/dashboard` for dashboard

## 4) Start stack with tunnel

```bash
docker compose --env-file .env.microservices -f docker-compose.microservices.yml --profile cloudflare up -d --build
```

## 5) Recommended security settings

- Enable Cloudflare Access policy on `dashboard.your-domain.com`.
- Force HTTPS and HSTS at Cloudflare edge.
- Set WAF managed rules to "On".
- Restrict backend access to internal Docker network only (already configured).
- Rotate secrets in `Backend/.env` and `twinforge/services/Convesation_and_orchestrator_agents/.env`.
