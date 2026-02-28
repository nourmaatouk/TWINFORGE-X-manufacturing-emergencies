<# 
.SYNOPSIS
    Deploy TWINFORGE to Azure Container Apps - Bulletproof v4
.DESCRIPTION
    Idempotent script: re-run safely at any point.
    Builds Docker images, pushes to ACR, deploys 10 Container Apps.
.PARAMETER ResourceGroup
    Azure Resource Group name
.PARAMETER AcrName
    Azure Container Registry name (must be globally unique, lowercase alphanumeric)
.PARAMETER EnvName
    Container Apps Environment name
.PARAMETER SkipBuild
    Skip Docker build+push (images already in ACR)
.EXAMPLE
    .\deploy-azure.ps1
    .\deploy-azure.ps1 -SkipBuild
    .\deploy-azure.ps1 -AcrName myacr123 -ResourceGroup my-rg
#>

param(
    [string]$ResourceGroup = "twinforge-rg",
    [string]$Location      = "eastus",
    [string]$AcrName       = "twinforgeacr20260220",
    [string]$EnvName       = "twinforge-env",
    [switch]$SkipBuild
)

# CRITICAL: Do NOT use "Stop" -- az CLI writes info/progress to stderr
# which PowerShell 5.1 treats as terminating errors when ErrorActionPreference=Stop
$ErrorActionPreference = "Continue"
$env:AZURE_CORE_ONLY_SHOW_ERRORS = "True"

# -- Helper: run az and fail on non-zero exit code --
function Run-Az {
    param([string]$Label, [string]$Cmd)
    Write-Host "  $Label" -ForegroundColor Gray
    $output = Invoke-Expression "& $Cmd 2>&1" | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] $Label" -ForegroundColor Red
        Write-Host $output -ForegroundColor DarkRed
        throw "Azure CLI failed: $Label (exit code $LASTEXITCODE)"
    }
    return $output.Trim()
}

# -- Helper: run az silently, ignore errors (for idempotent creates) --
function Run-Az-Safe {
    param([string]$Label, [string]$Cmd)
    Write-Host "  $Label" -ForegroundColor Gray
    $output = Invoke-Expression "& $Cmd 2>&1" | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    (already exists or warning - continuing)" -ForegroundColor DarkYellow
    }
    return $output.Trim()
}

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..\").Path
Set-Location $ProjectRoot

# -------------------------------------------------------------------------
# LOAD SECRETS
# -------------------------------------------------------------------------
if (-not $env:MESSAGE_SIGNING_KEY) {
    $env:MESSAGE_SIGNING_KEY = -join ((48..57) + (97..102) | Get-Random -Count 64 | ForEach-Object { [char]$_ })
    Write-Host "[INFO] Generated MESSAGE_SIGNING_KEY" -ForegroundColor Gray
}
if (-not $env:REDIS_PASSWORD) {
    $env:REDIS_PASSWORD = -join ((48..57) + (97..102) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
    Write-Host "[INFO] Generated REDIS_PASSWORD" -ForegroundColor Gray
}
$MessageSigningKey = $env:MESSAGE_SIGNING_KEY
$RedisPassword     = $env:REDIS_PASSWORD

$backendEnv = Join-Path $ProjectRoot "Backend\.env"
if (Test-Path $backendEnv) {
    Get-Content $backendEnv | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $k = $Matches[1].Trim(); $v = $Matches[2].Trim()
            if ($k -in @("JWT_SECRET","OTP_SECRET","DATA_ENCRYPTION_KEYS","ACTIVE_ENCRYPTION_KEY_ID","RESEND_API_KEY","RESEND_FROM","LOGIN_EMAIL","LOGIN_PASSWORD")) {
                [Environment]::SetEnvironmentVariable($k, $v, "Process")
            }
        }
    }
    Write-Host "[INFO] Loaded secrets from Backend/.env" -ForegroundColor Gray
}

$AcrServer = "$AcrName.azurecr.io"

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "   TWINFORGE - Azure Container Apps Deployment v4"       -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Resource Group : $ResourceGroup"                       -ForegroundColor White
Write-Host "  ACR            : $AcrServer"                           -ForegroundColor White
Write-Host "  Environment    : $EnvName"                             -ForegroundColor White
Write-Host "  Skip Build     : $SkipBuild"                           -ForegroundColor White
Write-Host ""

# =========================================================================
# STEP 1 - Resource Group
# =========================================================================
Write-Host "[1/9] Resource Group..." -ForegroundColor Yellow

$rgCheck = az group exists --name $ResourceGroup -o tsv 2>&1 | Out-String
if ($rgCheck.Trim() -eq "true") {
    $Location = (az group show --name $ResourceGroup --query location -o tsv 2>&1 | Out-String).Trim()
    Write-Host "  [OK] Existing RG '$ResourceGroup' in $Location" -ForegroundColor Green
} else {
    Run-Az "Creating resource group..." "az group create --name $ResourceGroup --location $Location --output none"
    Write-Host "  [OK] Created '$ResourceGroup' in $Location" -ForegroundColor Green
}

# =========================================================================
# STEP 2 - Azure Container Registry
# =========================================================================
Write-Host "[2/9] Azure Container Registry..." -ForegroundColor Yellow

Run-Az-Safe "Creating/verifying ACR..." "az acr create --name $AcrName --resource-group $ResourceGroup --sku Basic --admin-enabled true --output none"

# Login to ACR
Write-Host "  Logging into ACR..." -ForegroundColor Gray
$loginOut = az acr login --name $AcrName 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ACR login via az failed, trying docker login..." -ForegroundColor DarkYellow
    $credJson = az acr credential show --name $AcrName -o json 2>&1 | Out-String
    $creds = $credJson | ConvertFrom-Json
    docker login $AcrServer -u $creds.username -p $creds.passwords[0].value 2>&1 | Out-Null
}
Write-Host "  [OK] ACR '$AcrServer'" -ForegroundColor Green

# =========================================================================
# STEP 3 - Build and Push Docker Images
# =========================================================================
Write-Host "[3/9] Docker images..." -ForegroundColor Yellow

if ($SkipBuild) {
    Write-Host "  [SKIP] -SkipBuild flag set, using existing images in ACR" -ForegroundColor DarkYellow
} else {
    $images = @(
        @{ Name="auth-backend";        Context="Backend";                                                Dockerfile="Dockerfile"; Args=@() },
        @{ Name="auth-frontend";       Context="Frontend/vite-project";                                  Dockerfile="Dockerfile"; Args=@("NGINX_CONF=azure.conf","VITE_API_URL=/api","VITE_DASHBOARD_URL=/dashboard/") },
        @{ Name="twinforge-dashboard"; Context="twinforge/services/Convesation_and_orchestrator_agents"; Dockerfile="Dockerfile"; Args=@() },
        @{ Name="agent-data-iot";      Context="twinforge/services/agent-data-iot";                      Dockerfile="Dockerfile"; Args=@() },
        @{ Name="agent-verifier";      Context="twinforge/services/agent-verifier";                      Dockerfile="Dockerfile"; Args=@() },
        @{ Name="agent-security";      Context="twinforge/services/agent-security";                      Dockerfile="Dockerfile"; Args=@() },
        @{ Name="mcp-mock-server";     Context="twinforge/services/mcp-mock-server";                     Dockerfile="Dockerfile"; Args=@() },
        @{ Name="dataset-replay";      Context="twinforge/services/dataset-replay";                      Dockerfile="Dockerfile"; Args=@() },
        @{ Name="mosquitto";           Context="deploy/azure/mosquitto";                                 Dockerfile="Dockerfile"; Args=@() }
    )

    foreach ($img in $images) {
        $tag = "$AcrServer/$($img.Name):latest"
        Write-Host "  Building $($img.Name)..." -ForegroundColor Gray

        $buildArgs = ($img.Args | ForEach-Object { "--build-arg $_" }) -join " "
        $dockerBuild = "docker build -t `"$tag`" -f `"$($img.Context)/$($img.Dockerfile)`" $buildArgs `"$($img.Context)`""
        Invoke-Expression $dockerBuild
        if ($LASTEXITCODE -ne 0) { throw "Docker build failed: $($img.Name)" }

        # Push with retry
        $pushed = $false
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            Write-Host "  Pushing $($img.Name) (attempt $attempt/3)..." -ForegroundColor Gray
            docker push $tag 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { $pushed = $true; break }
            if ($attempt -lt 3) { Start-Sleep -Seconds 10 }
        }
        if (-not $pushed) { throw "Failed to push $($img.Name) after 3 attempts" }
        Write-Host "  [OK] $($img.Name)" -ForegroundColor Green
    }
    Write-Host "  [OK] All 9 images in ACR" -ForegroundColor Green
}

# =========================================================================
# STEP 4 - Container Apps Environment
# =========================================================================
Write-Host "[4/9] Container Apps Environment..." -ForegroundColor Yellow

$envCheck = az containerapp env show --name $EnvName --resource-group $ResourceGroup -o tsv --query name 2>&1 | Out-String
if ($envCheck.Trim() -eq $EnvName) {
    Write-Host "  [OK] Environment '$EnvName' already exists" -ForegroundColor Green
} else {
    Write-Host "  Registering providers (this can take 1-2 min)..." -ForegroundColor Gray
    az provider register --namespace Microsoft.App --wait 2>&1 | Out-Null
    az provider register --namespace Microsoft.OperationalInsights --wait 2>&1 | Out-Null

    Write-Host "  Creating environment (this can take 2-5 min)..." -ForegroundColor Gray
    Run-Az "Creating Container Apps Environment..." "az containerapp env create --name $EnvName --resource-group $ResourceGroup --location $Location --output none"
    Write-Host "  [OK] Environment '$EnvName' created" -ForegroundColor Green
}

# =========================================================================
# STEP 5 - ACR Credentials
# =========================================================================
Write-Host "[5/9] ACR credentials..." -ForegroundColor Yellow
$credJson = az acr credential show --name $AcrName -o json 2>&1 | Out-String
$AcrCreds = $credJson | ConvertFrom-Json
$AcrUser  = $AcrCreds.username
$AcrPass  = $AcrCreds.passwords[0].value
Write-Host "  [OK] Credentials for '$AcrUser'" -ForegroundColor Green

# =========================================================================
# STEP 6 - Deploy Infrastructure (Redis + Mosquitto)
# =========================================================================
Write-Host "[6/9] Infrastructure (Redis + Mosquitto)..." -ForegroundColor Yellow

# Redis needs direct invocation (--args uses comma-separated values that break Invoke-Expression)
Write-Host "  Deploying Redis..." -ForegroundColor Gray
az containerapp create --name redis --resource-group $ResourceGroup --environment $EnvName --image "redis:7-alpine" --args "redis-server","--requirepass","$RedisPassword" --target-port 6379 --transport tcp --exposed-port 6379 --ingress internal --min-replicas 1 --max-replicas 1 --cpu 0.25 --memory 0.5Gi --output none 2>&1 | Out-String | Out-Null

Run-Az-Safe "Deploying Mosquitto..." "az containerapp create --name mosquitto --resource-group $ResourceGroup --environment $EnvName --image $AcrServer/mosquitto:latest --registry-server $AcrServer --registry-username $AcrUser --registry-password $AcrPass --target-port 1883 --transport tcp --exposed-port 1883 --ingress internal --min-replicas 1 --max-replicas 1 --cpu 0.25 --memory 0.5Gi --output none"

Write-Host "  [OK] Infrastructure deployed" -ForegroundColor Green

# =========================================================================
# STEP 7 - Deploy Application Services
# =========================================================================
Write-Host "[7/9] Application services..." -ForegroundColor Yellow

$RedisUrl = "redis://:${RedisPassword}@redis:6379"

# -- auth-backend --
$abEnv = @(
    "NODE_ENV=production",
    "AUTH_DB_PATH=/data/auth.db",
    "JWT_SECRET=$($env:JWT_SECRET)",
    "OTP_SECRET=$($env:OTP_SECRET)",
    "DATA_ENCRYPTION_KEYS=$($env:DATA_ENCRYPTION_KEYS)",
    "ACTIVE_ENCRYPTION_KEY_ID=$($env:ACTIVE_ENCRYPTION_KEY_ID)",
    "RESEND_API_KEY=$($env:RESEND_API_KEY)",
    "RESEND_FROM=$($env:RESEND_FROM)",
    "LOGIN_EMAIL=$($env:LOGIN_EMAIL)",
    "LOGIN_PASSWORD=$($env:LOGIN_PASSWORD)",
    "TRUST_PROXY=1",
    "APP_ORIGIN=https://PLACEHOLDER",
    "APP_ORIGINS=https://PLACEHOLDER",
    "DASHBOARD_URL=https://PLACEHOLDER/dashboard/"
) -join " "

Run-Az-Safe "Deploying auth-backend..." "az containerapp create --name auth-backend --resource-group $ResourceGroup --environment $EnvName --image $AcrServer/auth-backend:latest --registry-server $AcrServer --registry-username $AcrUser --registry-password $AcrPass --target-port 5000 --ingress internal --min-replicas 1 --max-replicas 3 --cpu 0.5 --memory 1.0Gi --env-vars $abEnv --output none"
# If the app already exists, create is skipped; force latest image rollout.
Run-Az "Refreshing auth-backend image revision..." "az containerapp update --name auth-backend --resource-group $ResourceGroup --image $AcrServer/auth-backend:latest --output none"
Run-Az "Allowing HTTP on auth-backend internal ingress..." "az containerapp ingress update --name auth-backend --resource-group $ResourceGroup --type internal --target-port 5000 --transport auto --allow-insecure true --output none"

# -- twinforge-dashboard --
Run-Az-Safe "Deploying twinforge-dashboard..." "az containerapp create --name twinforge-dashboard --resource-group $ResourceGroup --environment $EnvName --image $AcrServer/twinforge-dashboard:latest --registry-server $AcrServer --registry-username $AcrUser --registry-password $AcrPass --target-port 8001 --ingress internal --min-replicas 1 --max-replicas 3 --cpu 0.5 --memory 1.0Gi --env-vars AUTH_BACKEND_URL=http://auth-backend AUTH_LOGIN_URL=https://PLACEHOLDER REDIS_URL=$RedisUrl MESSAGE_SIGNING_KEY=$MessageSigningKey --output none"
Run-Az "Allowing HTTP on twinforge-dashboard internal ingress..." "az containerapp ingress update --name twinforge-dashboard --resource-group $ResourceGroup --type internal --target-port 8001 --transport auto --allow-insecure true --output none"

# -- agent-data-iot --
Run-Az-Safe "Deploying agent-data-iot..." "az containerapp create --name agent-data-iot --resource-group $ResourceGroup --environment $EnvName --image $AcrServer/agent-data-iot:latest --registry-server $AcrServer --registry-username $AcrUser --registry-password $AcrPass --target-port 8003 --ingress internal --min-replicas 1 --max-replicas 3 --cpu 0.5 --memory 1.0Gi --env-vars REDIS_URL=$RedisUrl MESSAGE_SIGNING_KEY=$MessageSigningKey MQTT_BROKER_HOST=mosquitto MQTT_BROKER_PORT=1883 SECURITY_AGENT_URL=http://agent-security AGENT_ID=agent_3 SERVICE_PORT=8003 LOG_LEVEL=INFO --output none"

# -- agent-verifier --
Run-Az-Safe "Deploying agent-verifier..." "az containerapp create --name agent-verifier --resource-group $ResourceGroup --environment $EnvName --image $AcrServer/agent-verifier:latest --registry-server $AcrServer --registry-username $AcrUser --registry-password $AcrPass --target-port 8004 --ingress internal --min-replicas 1 --max-replicas 3 --cpu 0.5 --memory 1.0Gi --env-vars REDIS_URL=$RedisUrl MESSAGE_SIGNING_KEY=$MessageSigningKey SECURITY_AGENT_URL=http://agent-security AGENT_ID=agent_4 PORT=8004 --output none"

# -- agent-security --
$secAgentUrls = "agent_1=http://twinforge-dashboard,agent_2=http://twinforge-dashboard,agent_3=http://agent-data-iot,agent_4=http://agent-verifier"
Run-Az-Safe "Deploying agent-security..." "az containerapp create --name agent-security --resource-group $ResourceGroup --environment $EnvName --image $AcrServer/agent-security:latest --registry-server $AcrServer --registry-username $AcrUser --registry-password $AcrPass --target-port 8005 --ingress internal --min-replicas 1 --max-replicas 3 --cpu 0.5 --memory 1.0Gi --env-vars REDIS_URL=$RedisUrl MESSAGE_SIGNING_KEY=$MessageSigningKey AGENT_ID=agent_5 PORT=8005 LOCKDOWN_ENABLED=true ALLOWED_IPS=0.0.0.0/0,::0/0 AGENT_URLS=$secAgentUrls --output none"

# -- mcp-mock-server --
Run-Az-Safe "Deploying mcp-mock-server..." "az containerapp create --name mcp-mock-server --resource-group $ResourceGroup --environment $EnvName --image $AcrServer/mcp-mock-server:latest --registry-server $AcrServer --registry-username $AcrUser --registry-password $AcrPass --target-port 9001 --ingress internal --min-replicas 1 --max-replicas 1 --cpu 0.25 --memory 0.5Gi --output none"

# -- dataset-replay --
Run-Az-Safe "Deploying dataset-replay..." "az containerapp create --name dataset-replay --resource-group $ResourceGroup --environment $EnvName --image $AcrServer/dataset-replay:latest --registry-server $AcrServer --registry-username $AcrUser --registry-password $AcrPass --min-replicas 1 --max-replicas 1 --cpu 0.25 --memory 0.5Gi --env-vars AGENT_DATA_IOT_URL=http://agent-data-iot REPLAY_SPEED=1.0 REPLAY_INTERVAL_SEC=2.0 BATCH_SIZE=5 --output none"

Write-Host "  [OK] All application services deployed" -ForegroundColor Green

# =========================================================================
# STEP 8 - Frontend (External Ingress - the ONLY public service)
# =========================================================================
Write-Host "[8/9] Frontend (public ingress)..." -ForegroundColor Yellow

$AuthBackendHost = "auth-backend"
$DashboardHost = "twinforge-dashboard"

Run-Az-Safe "Deploying auth-frontend..." "az containerapp create --name auth-frontend --resource-group $ResourceGroup --environment $EnvName --image $AcrServer/auth-frontend:latest --registry-server $AcrServer --registry-username $AcrUser --registry-password $AcrPass --target-port 80 --ingress external --min-replicas 1 --max-replicas 5 --cpu 0.25 --memory 0.5Gi --env-vars AUTH_BACKEND_HOST=$AuthBackendHost DASHBOARD_HOST=$DashboardHost --output none"
# If the app already exists, create is skipped; force latest image rollout.
Run-Az "Refreshing auth-frontend image revision..." "az containerapp update --name auth-frontend --resource-group $ResourceGroup --image $AcrServer/auth-frontend:latest --set-env-vars AUTH_BACKEND_HOST=$AuthBackendHost DASHBOARD_HOST=$DashboardHost --output none"

Write-Host "  [OK] Frontend deployed" -ForegroundColor Green

# =========================================================================
# STEP 9 - Get Public FQDN and Update auth-backend + dashboard
# =========================================================================
Write-Host "[9/9] Configuring public URLs..." -ForegroundColor Yellow

$FQDN = (az containerapp show --name auth-frontend --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv 2>&1 | Out-String).Trim()
$PublicUrl = "https://$FQDN"

Run-Az "Updating auth-backend with real URL..." "az containerapp update --name auth-backend --resource-group $ResourceGroup --set-env-vars APP_ORIGIN=$PublicUrl APP_ORIGINS=$PublicUrl DASHBOARD_URL=$PublicUrl/dashboard/ --output none"

Run-Az "Updating twinforge-dashboard with real URL..." "az containerapp update --name twinforge-dashboard --resource-group $ResourceGroup --set-env-vars AUTH_LOGIN_URL=$PublicUrl --output none"

$healthUrl = "$PublicUrl/api/health"
$healthStatus = ""
try {
    $healthResponse = Invoke-WebRequest -Uri $healthUrl -Method Get -UseBasicParsing -TimeoutSec 20
    $healthStatus = "$($healthResponse.StatusCode)"
} catch {
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
        $healthStatus = "$([int]$_.Exception.Response.StatusCode.value__)"
    } else {
        $healthStatus = "unreachable"
    }
}
if ($healthStatus -ne "200") {
    Write-Host "  [WARN] Public auth API probe failed at $healthUrl (status: $healthStatus)" -ForegroundColor DarkYellow
} else {
    Write-Host "  [OK] Public auth API reachable at $healthUrl" -ForegroundColor Green
}

Write-Host "  [OK] URLs configured" -ForegroundColor Green

# =========================================================================
# DONE
# =========================================================================
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "         DEPLOYMENT COMPLETE                            " -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  App URL     : $PublicUrl"                               -ForegroundColor Cyan
Write-Host "  Dashboard   : $PublicUrl/dashboard/"                    -ForegroundColor Cyan
Write-Host ""
Write-Host "  Services (10):"                                         -ForegroundColor White
Write-Host "    auth-frontend  (external)"                            -ForegroundColor White
Write-Host "    auth-backend   (internal)"                            -ForegroundColor White
Write-Host "    twinforge-dashboard (internal)"                       -ForegroundColor White
Write-Host "    agent-data-iot, agent-verifier, agent-security"       -ForegroundColor White
Write-Host "    mcp-mock-server, dataset-replay"                      -ForegroundColor White
Write-Host "    redis, mosquitto"                                     -ForegroundColor White
Write-Host ""
Write-Host "  SAVE THESE:" -ForegroundColor Yellow
Write-Host "    MESSAGE_SIGNING_KEY = $MessageSigningKey"             -ForegroundColor Yellow
Write-Host "    REDIS_PASSWORD      = $RedisPassword"                 -ForegroundColor Yellow
Write-Host ""
