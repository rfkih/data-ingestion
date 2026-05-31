#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Sync ML artifacts from local blackheart-train to VPS inference service.

.DESCRIPTION
    Rsyncs C:\Project\blackheart-train\artifacts\ to /home/starsky/blackheart-train/artifacts/
    on the production VPS using tar-over-SSH (no rsync required on the runner).

    Run this script after every model training session, or schedule it hourly
    via Windows Task Scheduler so the VPS always has fresh artifacts.

.EXAMPLE
    .\scripts\sync-artifacts.ps1
    .\scripts\sync-artifacts.ps1 -DryRun
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$SshKey   = "C:\Project\sshkey.pem"
$SshUser  = "starsky"
$SshHost  = "202.74.75.3"
$LocalDir = "C:\Project\blackheart-train\artifacts"
$RemoteDir = "/home/starsky/blackheart-train/artifacts"

if (-not (Test-Path $SshKey)) {
    Write-Error "SSH key not found at $SshKey"
    exit 1
}

if (-not (Test-Path $LocalDir)) {
    Write-Warning "Local artifacts dir does not exist: $LocalDir  (nothing to sync)"
    exit 0
}

$artifacts = Get-ChildItem -Recurse $LocalDir -Filter "*.pkl"
if ($artifacts.Count -eq 0) {
    Write-Warning "No .pkl artifacts found in $LocalDir — nothing to sync."
    exit 0
}

Write-Host "Found $($artifacts.Count) artifact(s) to sync."

if ($DryRun) {
    Write-Host "[DRY RUN] Would sync $LocalDir → ${SshUser}@${SshHost}:${RemoteDir}"
    $artifacts | ForEach-Object { Write-Host "  $($_.Name)" }
    exit 0
}

# Ensure remote dir exists and is writable
$sshOpts = "-i `"$SshKey`" -o StrictHostKeyChecking=no -o BatchMode=yes"
Invoke-Expression "ssh $sshOpts ${SshUser}@${SshHost} `"mkdir -p $RemoteDir && chmod 755 $RemoteDir`""

# Pipe tar archive through SSH — no rsync needed on either side.
# We cd into the parent of artifacts/ so the archive preserves the
# sha[:2]/sha.pkl relative structure under the remote dir.
$parentDir = Split-Path $LocalDir -Parent
$baseName  = Split-Path $LocalDir -Leaf

Write-Host "Syncing $LocalDir → ${SshUser}@${SshHost}:${RemoteDir} ..."
$cmd = "tar czf - -C `"$parentDir`" `"$baseName`" | ssh $sshOpts ${SshUser}@${SshHost} `"tar xzf - -C /home/starsky/blackheart-train/`""
Invoke-Expression $cmd

if ($LASTEXITCODE -ne 0) {
    Write-Error "Artifact sync failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

# Verify on remote
$remoteCount = Invoke-Expression "ssh $sshOpts ${SshUser}@${SshHost} `"find $RemoteDir -name '*.pkl' | wc -l`""
Write-Host "Sync complete. VPS has $($remoteCount.Trim()) artifact(s)."
