#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One-command lifecycle management for the Blackheart docker-compose stack.

.DESCRIPTION
    Wraps `docker compose` with the workflow this project actually uses:
    cleaning up legacy standalone containers, warning when host processes are
    holding the published ports, and giving short subcommands for the common
    paths. Run with no arguments to see the help.

.EXAMPLE
    .\manage.ps1 up        # start everything
    .\manage.ps1 logs      # tail all logs
    .\manage.ps1 wipe      # nuke postgres/redis volumes (DESTRUCTIVE)
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet('up','down','restart','rebuild','status','logs','build','wipe','shell','psql','help')]
    [string]$Command = 'help',

    [Parameter(Position = 1)]
    [string]$Service
)

# Don't set $ErrorActionPreference='Stop' here. Native commands (docker, etc.)
# write progress to stderr; under PS5.1 strict mode, those lines get treated as
# terminating errors and abort the script mid-build. We rely on explicit
# $LASTEXITCODE checks instead.
Set-Location -Path $PSScriptRoot

# BuildKit's TTY progress UI writes to stderr, which PS5.1 mangles. Force the
# plain reporter, which writes to stdout in linear log lines.
$env:BUILDKIT_PROGRESS = 'plain'

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

function Test-DockerRunning {
    try {
        docker version --format '{{.Server.Version}}' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-Java {
    # IntelliJ Community + JBR is the most reliable JDK 21 on this machine.
    $jbr = Get-ChildItem 'C:\Program Files\JetBrains' -Directory -ErrorAction SilentlyContinue |
           ForEach-Object { Join-Path $_.FullName 'jbr\bin\java.exe' } |
           Where-Object { Test-Path $_ } |
           Select-Object -First 1
    if ($jbr) { return $jbr }

    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) {
        return "$env:JAVA_HOME\bin\java.exe"
    }

    foreach ($glob in 'C:\Program Files\Eclipse Adoptium\jdk-21*\bin\java.exe',
                       'C:\Program Files\Java\jdk-21*\bin\java.exe') {
        $hit = Get-ChildItem $glob -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }

    $cmd = Get-Command java -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Find-Node {
    foreach ($p in 'C:\Program Files\nodejs\node.exe', "$env:LOCALAPPDATA\Programs\nodejs\node.exe") {
        if (Test-Path $p) { return (Split-Path -Parent $p) }
    }
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd) { return (Split-Path -Parent $cmd.Source) }
    return $null
}

function Ensure-BackendJar {
    # Two JARs are produced:
    #  - bootJar         -> blackheart-0.0.1-SNAPSHOT.jar           (trading; no exclusions)
    #  - researchBootJar -> blackheart-research-0.0.1-SNAPSHOT.jar  (research; BlackheartResearchApplication main + trading classes excluded)
    # We avoid tradingBootJar because its exclude list (service/research/**)
    # drops ResearchControlService, which trading-side ResearchControlController
    # depends on. Profile gating alone gives us safe runtime separation.
    $tradingJar  = Join-Path $PSScriptRoot 'blackheart-trading-engine\build\libs\blackheart-0.0.1-SNAPSHOT.jar'
    $researchJar = Join-Path $PSScriptRoot 'blackheart-trading-engine\build\libs\blackheart-research-0.0.1-SNAPSHOT.jar'

    $needBuild = $false
    if (-not (Test-Path $tradingJar))  { Write-Host "  blackheart (trading) JAR missing -> building"; $needBuild = $true }
    if (-not (Test-Path $researchJar)) { Write-Host "  blackheart-research JAR missing -> building";  $needBuild = $true }

    if (-not $needBuild) {
        $oldest = (Get-Item $tradingJar, $researchJar | Sort-Object LastWriteTime | Select-Object -First 1).LastWriteTime
        $newer = Get-ChildItem -Recurse "$PSScriptRoot\blackheart-trading-engine\src\main\java" -Filter *.java |
                 Where-Object { $_.LastWriteTime -gt $oldest } | Select-Object -First 1
        if ($newer) {
            Write-Host "  blackheart source newer than JARs -> rebuilding"
            $needBuild = $true
        }
    }

    if (-not $needBuild) { Write-Host "  blackheart JARs up to date"; return }

    $java = Find-Java
    if (-not $java) { Write-Error "No Java 21 found. Install JDK 21 or open IntelliJ once to materialize its bundled JBR."; exit 1 }
    $oldJavaHome = $env:JAVA_HOME
    $env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $java)
    Push-Location "$PSScriptRoot\blackheart-trading-engine"
    & .\gradlew.bat bootJar researchBootJar -x test --no-daemon --console=plain --warning-mode=none
    $rc = $LASTEXITCODE
    Pop-Location
    $env:JAVA_HOME = $oldJavaHome
    if ($rc -ne 0) { Write-Error "Gradle tradingBootJar/researchBootJar failed."; exit $rc }
}

function Ensure-FrontendBuild {
    $next = Join-Path $PSScriptRoot 'blackridge-frontend\.next'
    if (Test-Path "$next\BUILD_ID") {
        $buildTime = (Get-Item "$next\BUILD_ID").LastWriteTime
        $newer = Get-ChildItem -Recurse "$PSScriptRoot\blackridge-frontend\src" |
                 Where-Object { $_.LastWriteTime -gt $buildTime } | Select-Object -First 1
        if (-not $newer) { Write-Host "  Blackridge .next up to date"; return }
        Write-Host "  Blackridge source newer than .next -> rebuilding"
    } else {
        Write-Host "  Blackridge .next missing -> building"
    }

    $nodeDir = Find-Node
    if (-not $nodeDir) { Write-Error "Node.js not found. Install with 'winget install OpenJS.NodeJS.LTS'."; exit 1 }
    $env:Path = "$nodeDir;$env:LOCALAPPDATA\npm-global;$env:Path"

    Push-Location "$PSScriptRoot\blackridge-frontend"
    if (-not (Test-Path 'node_modules')) {
        Write-Host "  pnpm install (first-time)"
        pnpm install --frozen-lockfile --reporter=append-only
        if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Error "pnpm install failed."; exit 1 }
    }
    # NEXT_PUBLIC_* values are inlined into the bundle at build time, so the
    # browser hits whatever URL was baked in here — not what compose declares
    # at container runtime. Root-relative (`/`) for API + Research means the
    # bundle uses whatever origin served the page — works for local
    # browsing (`http://localhost:3000` → calls `/api/...` on same host),
    # tailnet browsing (`http://100.70.209.64:3000`), and the public dev
    # Funnel URL (`https://middleware.tailbf9662.ts.net:8443`) without
    # rebuilding. WebSocket needs an explicit scheme+host, so it points at
    # the dev Funnel URL — when browsing locally the WS connects via tunnel
    # which adds a few ms but keeps the bundle uniform. Override with
    # $env:FRONTEND_API_URL / FRONTEND_WS_URL if your deployment differs.
    $apiUrl = if ($env:FRONTEND_API_URL) { $env:FRONTEND_API_URL } else { '/' }
    $wsUrl  = if ($env:FRONTEND_WS_URL)  { $env:FRONTEND_WS_URL  } else { 'wss://middleware.tailbf9662.ts.net:8443/ws' }
    $env:NEXT_PUBLIC_API_URL = $apiUrl
    $env:NEXT_PUBLIC_RESEARCH_URL = $apiUrl
    $env:NEXT_PUBLIC_WS_URL = $wsUrl
    $env:NODE_ENV = 'production'
    Write-Host "  Building frontend with API=$apiUrl, WS=$wsUrl"
    pnpm exec next build --no-lint
    $rc = $LASTEXITCODE
    Pop-Location
    if ($rc -ne 0) { Write-Error "next build failed."; exit $rc }
}

function Remove-LegacyStandaloneContainers {
    # Compose can't take over a container created by `docker run` - it errors with
    # "container name already in use". Detect any pre-existing standalone copies
    # of our service containers and remove them so compose can recreate cleanly.
    foreach ($n in @('blackheart-postgres','blackheart-redis','blackheart-app','blackheart-frontend')) {
        $exists = docker ps -a --filter "name=^/${n}$" --format '{{.Names}}' 2>$null
        if (-not $exists) { continue }
        # Is this container already compose-managed for our project? If yes, leave it -
        # compose will reconcile it. Otherwise it's a leftover from a `docker run`.
        $composeOwned = docker ps -a --filter "name=^/${n}$" --filter "label=com.docker.compose.project=blackheart" --format '{{.Names}}' 2>$null
        if (-not $composeOwned) {
            Write-Host "  removing legacy standalone container: $n"
            docker rm -f $n | Out-Null
        }
    }
}

function Test-HostPortsFree {
    $ports = @{ 8080 = 'blackheart (backend)'; 3000 = 'blackridge (frontend)'; 5432 = 'postgres'; 6379 = 'redis'; 8088 = 'blackheartjs (node middleware)' }
    $blocked = @()
    foreach ($p in $ports.Keys) {
        $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
        if ($conn) {
            $owners = $conn.OwningProcess | Sort-Object -Unique
            foreach ($pidNum in $owners) {
                $proc = Get-Process -Id $pidNum -ErrorAction SilentlyContinue
                if (-not $proc) { continue }
                # Skip Docker Desktop's own port-forwarders (docker-proxy on Linux/WSL2,
                # com.docker.backend / wslrelay on Windows, vpnkit on older builds).
                if ($proc.ProcessName -in @('com.docker.backend','docker-proxy','wslrelay','vpnkit','com.docker.service')) { continue }
                $blocked += [pscustomobject]@{ Port = $p; Use = $ports[$p]; Pid = $pidNum; Proc = $proc.ProcessName }
            }
        }
    }
    return ,$blocked
}

function Show-Help {
@'
Usage: .\manage.ps1 <command> [service]

Commands:
  up              Start the full stack (build images if missing)
  down            Stop the stack (data preserved in named volumes)
  restart         Restart all running services without recreating
  rebuild         Stop, rebuild images, start (use after code changes)
  build [svc]     Rebuild one or all images without starting
  status          Show service health + ports
  logs [svc]      Tail logs (omit svc for combined; ctrl+c to stop)
  shell <svc>     Open a shell inside a running container
  psql            Open a psql prompt against trading_db
  wipe            DESTRUCTIVE: stop stack and delete postgres/redis volumes
  help            Show this message

Services: postgres | redis | blackheart | blackheart-research | blackheartjs | blackridge

Examples:
  .\manage.ps1 up
  .\manage.ps1 logs blackheart
  .\manage.ps1 rebuild           # after editing Java/TS source
  .\manage.ps1 shell blackheart
  .\manage.ps1 psql
'@ | Write-Host
}

# ----------------------------------------------------------------------------
# Pre-flight
# ----------------------------------------------------------------------------

if (-not (Test-DockerRunning)) {
    Write-Error "Docker doesn't appear to be running. Start Docker Desktop first."
    exit 1
}

# ----------------------------------------------------------------------------
# Subcommands
# ----------------------------------------------------------------------------

switch ($Command) {

    'up' {
        Write-Host ">> pre-flight: build artifacts" -ForegroundColor Cyan
        Ensure-BackendJar
        Ensure-FrontendBuild

        Remove-LegacyStandaloneContainers

        $blocked = Test-HostPortsFree
        if ($blocked.Count -gt 0) {
            Write-Warning "Host processes are holding published ports - compose will fail to bind:"
            $blocked | Format-Table -AutoSize
            Write-Host 'Stop them with:  Stop-Process -Id <pid> -Force' -ForegroundColor Yellow
            Write-Host "Or remove them yourself, then re-run:  .\manage.ps1 up" -ForegroundColor Yellow
            exit 1
        }

        Write-Host ">> docker compose up -d --build" -ForegroundColor Cyan
        docker compose up -d --build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

        Write-Host ""
        Write-Host "Stack started. Frontend at http://localhost:3000  |  Backend at http://localhost:8080" -ForegroundColor Green
        Write-Host "  .\manage.ps1 status   --see service health" -ForegroundColor DarkGray
        Write-Host "  .\manage.ps1 logs     --tail logs" -ForegroundColor DarkGray
    }

    'down' {
        Write-Host ">> docker compose down" -ForegroundColor Cyan
        docker compose down
    }

    'restart' {
        Write-Host ">> docker compose restart $Service" -ForegroundColor Cyan
        if ($Service) { docker compose restart $Service } else { docker compose restart }
    }

    'rebuild' {
        Write-Host ">> docker compose down" -ForegroundColor Cyan
        docker compose down
        Write-Host ">> docker compose up -d --build" -ForegroundColor Cyan
        docker compose up -d --build
    }

    'build' {
        Write-Host ">> docker compose build $Service --progress=plain" -ForegroundColor Cyan
        if ($Service) { docker compose build $Service --progress=plain } else { docker compose build --progress=plain }
    }

    'status' {
        docker compose ps
    }

    'logs' {
        Write-Host "Tailing logs (ctrl+c to stop)..." -ForegroundColor DarkGray
        if ($Service) {
            docker compose logs -f --tail=100 $Service
        } else {
            docker compose logs -f --tail=50
        }
    }

    'shell' {
        if (-not $Service) { Write-Error "shell requires a service name (postgres|redis|blackheart|blackridge)"; exit 1 }
        docker compose exec $Service sh
    }

    'psql' {
        docker compose exec -e PGPASSWORD=admin postgres psql -U postgres -d trading_db
    }

    'wipe' {
        Write-Warning "This will DELETE all data in postgres + redis volumes."
        $resp = Read-Host "Type 'yes' to continue"
        if ($resp -ne 'yes') { Write-Host "Aborted."; exit 1 }
        docker compose down -v
        Write-Host "Volumes wiped. Run '.\manage.ps1 up' to rebuild from scratch." -ForegroundColor Green
    }

    default { Show-Help }
}
