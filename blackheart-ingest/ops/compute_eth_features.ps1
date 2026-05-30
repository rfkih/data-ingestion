# Recurring ETH bar-feature compute -> VPS primary (Tailscale).
#
# WHY: the inference streaming worker turns feature_values into signal_history
# for the live regime_eth_v2 ML gate (strategy DCB-ETHUSDT-1h). The ingest
# server's auto-compute loop only refreshes MACRO features, never these 9
# per-bar ETH features. Without this task they go stale, signal_history stops
# advancing, and the live ML gate silently FAILS OPEN (trades ungated). The
# MlSignalStale vmalert rule is the safety net; this task is the actual fix.
#
# Run hourly via Task Scheduler. Writes to the VPS primary at the home
# box's Tailscale peer; the home standby replica then gets the rows via
# streaming replication automatically.
#
# Secret handling: the DB password is read from the User env var
# BLACKHEART_VPS_DB_PASSWORD (set once via SetEnvironmentVariable) so no
# plaintext credential lives in this file or in git.
#
# --days 40 is deliberate: the widest rolling feature (btc_realized_vol_30d,
# 720-bar window) needs ~31d of in-window lookback to compute the latest bar.
# A short window starves it and the signal lags one bar permanently.

$ErrorActionPreference = 'Stop'

$pw = [Environment]::GetEnvironmentVariable('BLACKHEART_VPS_DB_PASSWORD','User')
if ([string]::IsNullOrWhiteSpace($pw)) {
    Write-Error "BLACKHEART_VPS_DB_PASSWORD User env var is not set; aborting."
    exit 2
}

$env:INGEST_DB_HOST     = '100.112.13.126'
$env:INGEST_DB_PORT     = '5432'
$env:INGEST_DB_NAME     = 'trading_db'
$env:INGEST_DB_USER     = 'blackheart_trading'
$env:INGEST_DB_PASSWORD = $pw

$repo   = Split-Path -Parent $PSScriptRoot          # C:\Project\blackheart-ingest
$python = Join-Path $repo '.venv\Scripts\python.exe'
$log    = Join-Path $PSScriptRoot 'compute_eth_features.log'

$features = 'btc_atr_ratio_14_24,btc_log_return_1h,btc_log_return_24h,btc_log_return_4h,btc_realized_vol_30d,btc_realized_vol_7d,btc_rsi_14_1h,btc_volume_zscore_24h,btc_volume_zscore_4h'

$stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
Add-Content -Path $log -Value "===== $stamp  compute start ====="

# Python logging writes to stderr. Under PowerShell 5.1, piping native stderr
# into the PS pipeline with ErrorActionPreference='Stop' wraps each line in a
# NativeCommandError and aborts. Redirect both streams straight to the log file
# and lower EAP for the native call so the real python exit code drives success.
Push-Location $repo
$ErrorActionPreference = 'Continue'
try {
    & $python -m blackheart_ingest.workers.compute_features `
        --features $features --symbol ETHUSDT --interval 1h --days 40 *>> $log
    $code = $LASTEXITCODE
} finally {
    $ErrorActionPreference = 'Stop'
    Pop-Location
}
Add-Content -Path $log -Value "----- exit=$code -----"

# Keep the log from growing without bound — trim to the last ~2000 lines.
if (Test-Path $log) {
    $lines = Get-Content $log
    if ($lines.Count -gt 2000) { $lines[-2000..-1] | Set-Content $log }
}

exit $code
