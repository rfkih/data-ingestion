# Blackheart loop DEAD-MAN'S-SWITCH — off-host watcher (runs on the dev PC via Task Scheduler).
# Independent of the VPS, so it catches BOTH failure modes the on-host heartbeat cannot:
#   - VPS unreachable (host down / network / docker dead)  -> ssh/psql fails
#   - loop silently dead (daily_cycle/heartbeat cron stopped) -> newest loop_report goes stale
# Alerts the operator on Telegram (creds held locally so the alert works even when the VPS is down).
$ErrorActionPreference = "Stop"
$cfgPath = Join-Path $env:USERPROFILE ".blackheart\deadman.env"
$logPath = Join-Path $env:USERPROFILE ".blackheart\deadman.log"
$inv = [Globalization.CultureInfo]::InvariantCulture
$stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

$cfg = @{}
foreach ($l in Get-Content $cfgPath) {
    if ($l -match '^\s*([^#=]+)=(.*)$') { $cfg[$matches[1].Trim()] = $matches[2].Trim() }
}
$token = $cfg["TELEGRAM_BOT_TOKEN"]; $chat = $cfg["TELEGRAM_CHAT_ID"]
$key = $cfg["VPS_SSH_KEY"]; $vps = $cfg["VPS_HOST"]
$thr = [double]::Parse($cfg["THRESHOLD_HOURS"], $inv)

function Send-Alert($msg) {
    if (-not ($token -and $chat)) { return }
    try {
        Invoke-RestMethod -Method Post -TimeoutSec 20 `
            -Uri "https://api.telegram.org/bot$token/sendMessage" `
            -Body @{ chat_id = $chat; text = $msg } | Out-Null
    } catch {}
}
function Write-Log($s) { "$stamp $s" | Out-File -Append -Encoding ASCII $logPath }

# Hours since the newest loop_report. base64-wrap the remote command to dodge PS/SSH quoting; -n
# prevents ssh from blocking on stdin in a non-console (scheduled-task) context.
$remote = 'docker exec blackheart-postgres psql -U postgres -d trading_db -t -A -c "select round(extract(epoch from (now()-max(created_time)))/3600,1) from loop_report;"'
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remote))
$age = & ssh -n -i $key -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 $vps "echo $b64 | base64 -d | bash" 2>$null
$ok = ($LASTEXITCODE -eq 0)

if (-not $ok) {
    Send-Alert "DEADMAN $stamp`nVPS UNREACHABLE (ssh/psql failed) - Blackheart loop status unknown. Check the VPS (202.74.75.3)."
    Write-Log "ALERT unreachable"
    exit 0
}
$age = ("$age").Trim()
if (-not $age) { Write-Log "ok (no loop_report rows yet)"; exit 0 }
$ageNum = [double]::Parse($age, $inv)
if ($ageNum -gt $thr) {
    Send-Alert "DEADMAN $stamp`nNo fresh loop_report in $ageNum h (> $thr h) - daily_cycle/heartbeat may be DEAD. Check the VPS cron."
    Write-Log "ALERT stale ${ageNum}h"
} else {
    Write-Log "ok ${ageNum}h"
}
