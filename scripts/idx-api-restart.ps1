# Restart the local IDX ingest API (uvicorn :8001) on the current code, with blackheart-ingest\idx-local.env loaded.
#   .\scripts\idx-api-restart.ps1
# Logs: logs\idx\api.out.log / api.err.log. The scheduler is a separate Windows task ("Blackheart IDX scheduler"):
# restart it too after a code change (Stop-ScheduledTask / Start-ScheduledTask).
$root = Split-Path -Parent $PSScriptRoot
$c = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($c) { Stop-Process -Id $c.OwningProcess -Force -Confirm:$false; Start-Sleep 2; "stopped pid $($c.OwningProcess)" }
$env:PYTHONIOENCODING = 'utf-8'
Get-Content (Join-Path $root "blackheart-ingest\idx-local.env") | Where-Object { $_ -match '^[A-Za-z_]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($k, $v, 'Process')
}
New-Item -ItemType Directory -Force (Join-Path $root "logs\idx") | Out-Null
$p = Start-Process -FilePath (Join-Path $root "blackheart-ingest\.venv\Scripts\python.exe") `
    -ArgumentList "-m uvicorn blackheart_ingest.workers.server:app --host 127.0.0.1 --port 8001" `
    -WorkingDirectory (Join-Path $root "blackheart-ingest") -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $root "logs\idx\api.out.log") -RedirectStandardError (Join-Path $root "logs\idx\api.err.log")
Start-Sleep 6
"api pid $($p.Id)"
try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/idx/ops -TimeoutSec 10).StatusCode } catch { "not up yet: $($_.Exception.Message)" }
