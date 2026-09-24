# Register (or remove) the Stockbit datafeed collector as a Windows scheduled task.
#   .\scripts\idx-feed-task.ps1            # register: at logon + a 10-min watchdog, hidden, restarts if it dies
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
# Two triggers. At logon, and a watchdog that re-fires every 10 minutes forever: this box is never logged out (uptime is
# measured in weeks), so a collector that is killed - by a stray "kill the python processes" restart, an OOM, anything -
# used to stay dead until the next logon and the desk woke up blind the next morning. MultipleInstances=IgnoreNew makes a
# start while it is already running a no-op, and a second collector that finds the advisory lock held exits 0, so the
# watchdog costs nothing when the feed is healthy and brings it back within 10 minutes when it is not.
function New-ScheduledTaskWatchdogTrigger {
    # Fires at midnight and every 10 minutes after it. Task Scheduler's "repeat indefinitely" cannot be expressed through
    # New-ScheduledTaskTrigger ([TimeSpan]::MaxValue registers as P99999999D and is rejected), so the daily trigger carries
    # a 23h50m repetition and the next midnight picks it up again - the gap never exceeds the 10-minute interval.
    $t = New-ScheduledTaskTrigger -Daily -At 00:00
    $t.Repetition = (New-ScheduledTaskTrigger -Once -At 00:00 -RepetitionInterval (New-TimeSpan -Minutes 10) `
        -RepetitionDuration (New-TimeSpan -Hours 23 -Minutes 50)).Repetition
    $t
}
$triggers = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME),
    (New-ScheduledTaskWatchdogTrigger)
)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
# -ErrorAction Stop: a rejected task XML used to print "registered + started" anyway and leave the old
# definition in place, which is how a broken trigger can hide for weeks.
Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings -Force -ErrorAction Stop | Out-Null
Start-ScheduledTask -TaskName $name
"registered + started '$name' (at logon + 10-min watchdog, hidden, restart 2 min). log: $log"
"remove with: .\scripts\idx-feed-task.ps1 -Remove"
