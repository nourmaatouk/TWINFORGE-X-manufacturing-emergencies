param(
    [ValidateSet("local", "docker", "docker-cloudflare", "stop")]
    [string]$Mode = "docker"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Ensure-EnvFile {
    if (-not (Test-Path "$root/.env.microservices")) {
        Copy-Item "$root/.env.microservices.example" "$root/.env.microservices"
        Write-Host "Created .env.microservices from example. Update values before production use."
    }
}

switch ($Mode) {
    "local" {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root/Backend'; npm install; npm run start"
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root/Frontend/vite-project'; npm install; npm run dev -- --host 0.0.0.0 --port 18080"
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root/twinforge/services/Convesation_and_orchestrator_agents'; python -m pip install -r requirements.txt; python run.py"
        Write-Host "Local services started in new terminals."
    }
    "docker" {
        Ensure-EnvFile
        Set-Location $root
        docker compose --env-file .env.microservices -f docker-compose.microservices.yml up -d --build
    }
    "docker-cloudflare" {
        Ensure-EnvFile
        Set-Location $root
        docker compose --env-file .env.microservices -f docker-compose.microservices.yml --profile cloudflare up -d --build
    }
    "stop" {
        Set-Location $root
        docker compose --env-file .env.microservices -f docker-compose.microservices.yml down
    }
}
