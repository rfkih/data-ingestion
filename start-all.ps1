#!/usr/bin/env pwsh
# start-all.ps1 — Start (or restart) all Blackheart services.
#
# Usage:
#   .\start-all.ps1              # start everything (infra + JVMs + orchestrator)
#   .\start-all.ps1 -Build       # rebuild JARs first, then start everything
#   .\start-all.ps1 -NoInfra     # skip Postgres/Redis (already running)
#   .\start-all.ps1 -Only trading|research|orch   # restart one JVM/service only
#
# Services:
#   Postgres         :5432  docker  blackheart-postgres
#   Redis            :6379  docker  blackheart-redis
#   Trading JVM      :8080  JAR     blackheart-trading-*.jar
#   Research JVM     :8081  JAR     blackheart-research-*.jar
#   Research Orch    :8082  python  -m orchestrator

param(
    [switch]$Build,
    [switch]$NoInfra,
    [ValidateSet("trading","research","orch","")]
    [string]$Only = ""
)

$ErrorActionPreference = "Stop"

# ── Paths ─────────────────────────────────────────────────────────────────────
$ProjectDir      = "C:\Project"
$BlackheartDir   = "$ProjectDir\blackheart-trading-engine"
$OrchestratorDir = "$ProjectDir\blackheart-research-orchestrator"
$ComposeFile     = "$ProjectDir\docker-compose.yml"
$JavaExe         = "C:\Users\rifki\.jdks\ms-21.0.11\bin\java.exe"
$TradingJar      = "$BlackheartDir\build\libs\blackheart-trading-0.0.1-SNAPSHOT.jar"
$ResearchJar     = "$BlackheartDir\build\libs\blackheart-research-0.0.1-SNAPSHOT.jar"

# ── Colour helpers ────────────────────────────────────────────────────────────
function Write-Step { param($msg) Write-Host "  $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "  [OK]  $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  [!!]  $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  [ERR] $msg" -ForegroundColor Red }

# ── Kill any process listening on a TCP port ──────────────────────────────────
function Stop-PortProcess {
    param([int]$Port)
    $rows = netstat -ano | Select-String ":$Port\s" | Where-Object { $_ -match "LISTENING" }
    foreach ($row in $rows) {
        $pid = ($row.ToString().Trim() -split '\s+')[-1]
        if ($pid -match '^\d+$' -and [int]$pid -gt 0) {
            try {
                Stop-Process -Id ([int]$pid) -Force -ErrorAction SilentlyContinue
                Write-Warn "Killed PID $pid on :$Port"
            } catch { }
        }
    }
}

# ── Wait for HTTP endpoint to return non-error ────────────────────────────────
function Wait-Http {
    param([string]$Url, [int]$TimeoutSec = 120, [string]$Label = $Url)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    Write-Step "Waiting for $Label ..."
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($r.StatusCode -lt 400) { Write-Ok "$Label ($($r.StatusCode))"; return $true }
        } catch { }
        Start-Sleep -Seconds 3
    }
    Write-Fail "$Label did not come up within ${TimeoutSec}s"
    return $false
}

# ── Wait for a Docker container to be healthy ─────────────────────────────────
function Wait-DockerHealthy {
    param([string]$Container, [int]$TimeoutSec = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    Write-Step "Waiting for $Container to be healthy ..."
    while ((Get-Date) -lt $deadline) {
        $health = docker inspect --format "{{.State.Health.Status}}" $Container 2>$null
        if ($health -eq "healthy") { Write-Ok "$Container is healthy"; return $true }
        if ($health -eq "unhealthy") { Write-Fail "$Container is unhealthy"; return $false }
        Start-Sleep -Seconds 2
    }
    Write-Fail "$Container did not become healthy within ${TimeoutSec}s"
    return $false
}

# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Blackheart — start-all.ps1" -ForegroundColor White
Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray

# ── Optional build ────────────────────────────────────────────────────────────
if ($Build) {
    Write-Host ""
    Write-Host "  [BUILD] Compiling JARs ..." -ForegroundColor White
    Push-Location $BlackheartDir
    & ".\gradlew.bat" bootJar --quiet
    if ($LASTEXITCODE -ne 0) { Write-Fail "Gradle build failed. Aborting."; Pop-Location; exit 1 }
    Pop-Location
    Write-Ok "Build complete"
}

# ── Validate JARs ─────────────────────────────────────────────────────────────
if ($Only -eq "" -or $Only -in @("trading","research")) {
    foreach ($jar in @($TradingJar, $ResearchJar)) {
        if (-not (Test-Path $jar)) {
            Write-Fail "JAR not found: $jar"
            Write-Fail "Run: .\start-all.ps1 -Build"
            exit 1
        }
    }
}

# ── 1. Infrastructure (Postgres + Redis) ─────────────────────────────────────
if (-not $NoInfra -and $Only -eq "") {
    Write-Host ""
    Write-Host "  [INFRA] Starting Postgres + Redis ..." -ForegroundColor White

    docker compose -f $ComposeFile up -d postgres redis 2>&1 | ForEach-Object {
        if ($_ -match "Started|Running|healthy") { Write-Step $_ }
    }

    Wait-DockerHealthy "blackheart-postgres" -TimeoutSec 60 | Out-Null
    Wait-DockerHealthy "blackheart-redis"    -TimeoutSec 30 | Out-Null
}

# ── 2. Kill existing JVM / orchestrator processes ─────────────────────────────
Write-Host ""
Write-Host "  [STOP] Killing existing processes ..." -ForegroundColor White

$ports = switch ($Only) {
    "trading"  { @(8080) }
    "research" { @(8081) }
    "orch"     { @(8082) }
    default    { @(8080, 8081, 8082) }
}
foreach ($p in $ports) { Stop-PortProcess $p }
Start-Sleep -Seconds 1

# ── 3. Start JVMs and orchestrator ───────────────────────────────────────────
Write-Host ""
Write-Host "  [START] Launching services ..." -ForegroundColor White

if ($Only -eq "" -or $Only -eq "trading") {
    Start-Process -FilePath $JavaExe `
                  -ArgumentList "-Xms512m -Xmx2g -jar `"$TradingJar`" --spring.profiles.active=dev" `
                  -WorkingDirectory $BlackheartDir `
                  -WindowStyle Normal
    Write-Ok "Trading JVM      → http://localhost:8080"
}

if ($Only -eq "" -or $Only -eq "research") {
    Start-Process -FilePath $JavaExe `
                  -ArgumentList "-Xms512m -Xmx1500m -jar `"$ResearchJar`" --spring.profiles.active=dev,research --server.port=8081" `
                  -WorkingDirectory $BlackheartDir `
                  -WindowStyle Normal
    Write-Ok "Research JVM     → http://localhost:8081"
}

if ($Only -eq "" -or $Only -eq "orch") {
    $pythonBin = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    if (-not $pythonBin) {
        Write-Warn "python not found in PATH — orchestrator not started"
    } else {
        Start-Process -FilePath $pythonBin `
                      -ArgumentList "-m orchestrator" `
                      -WorkingDirectory $OrchestratorDir `
                      -WindowStyle Normal
        Write-Ok "Orchestrator     → http://localhost:8082"
    }
}

# ── 4. Health checks ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  [HEALTH] Waiting for services to come up ..." -ForegroundColor White

if ($Only -eq "" -or $Only -eq "trading") {
    Wait-Http "http://localhost:8080/actuator/health/liveness" -TimeoutSec 90 -Label "Trading JVM  :8080"
}
if ($Only -eq "" -or $Only -eq "research") {
    Wait-Http "http://localhost:8081/actuator/health/liveness" -TimeoutSec 90 -Label "Research JVM :8081"
}
if ($Only -eq "" -or $Only -eq "orch") {
    Wait-Http "http://localhost:8082/healthz" -TimeoutSec 30 -Label "Orchestrator :8082"
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  All services started." -ForegroundColor Green
Write-Host ""
Write-Host "  Postgres   :5432  (docker)" -ForegroundColor DarkGray
Write-Host "  Redis      :6379  (docker)" -ForegroundColor DarkGray
Write-Host "  Trading    :8080  → http://localhost:8080/actuator/health" -ForegroundColor DarkGray
Write-Host "  Research   :8081  → http://localhost:8081/actuator/health" -ForegroundColor DarkGray
Write-Host "  Orch       :8082  → http://localhost:8082/readyz" -ForegroundColor DarkGray
Write-Host ""
