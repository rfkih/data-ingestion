# Register (or remove) the Stockbit datafeed collector as a Windows scheduled task.
#   .\scripts\idx-feed-task.ps1            # register: runs at logon, hidden, restarts if it dies
#   .\scripts\idx-feed-task.ps1 -Remove    # unregister
#   .\scripts\idx-feed-task.ps1 -Status    # show state + last run (+ the collector's own heartbeat)
#   .\scripts\idx-feed-task.ps1 -Restart   # kill the running collector (Stop-ScheduledTask leaves the python child alive,
#                                          # which then keeps the advisory lock) and start the task again
# The task runs scripts\idx.ps1 feed run (asyncio collector, idles outside Mon-Fri 08:40-16:20 WIB); it logs to
# logs\idx\feed.log and keeps its heartbeat in idx.feed_status (`idx feed status`, GET /idx/feed/status).
param([switch]$Remove, [switch]$Status, [switch]$NoRaw, [switch]$Restart)

$name = "Blackheart IDX feed"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "logs\idx"
New-Item -ItemType Directory -Force $logDir | Out-Null
$wrapper = Join-Path $root "scripts\idx.ps1"
$log = Join-Path $logDir "feed.log"

if ($Status) {
    Get-ScheduledTask -TaskName $name -ErrorAction Stop | Format-List TaskName, State
    Get-ScheduledTaskInfo -TaskName $name | Format-List LastRunTime, LastTaskResult, NextRunTime
    & $wrapper feed status
    exit 0
}
function Stop-Collector {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'blackheart_ingest\.idx\.cli feed run' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false; "stopped collector pid $($_.ProcessId)" }
    Start-Sleep 2
}
if ($Restart) {
    Stop-Collector
    Start-ScheduledTask -TaskName $name
    "restarted '$name'"
    exit 0
}
if ($Remove) {
    Stop-Collector
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    "removed '$name'"
    exit 0
}

$rawArg = if ($NoRaw) { " --no-raw" } else { "" }
$cmd = "`$PSDefaultParameterValues['Out-File:Encoding']='utf8'; & '$wrapper' feed run$rawArg *>> '$log'"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$cmd`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $name
"registered + started '$name' (at logon, hidden, restart 2 min). log: $log"
"remove with: .\scripts\idx-feed-task.ps1 -Remove"
