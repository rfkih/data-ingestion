# Register (or remove) the IDX dead-man switch as its OWN Windows scheduled task (Track A1, 2026-09-26).
#   .\scripts\idx-watchdog-task.ps1            # register: every 10 minutes, hidden
#   .\scripts\idx-watchdog-task.ps1 -Remove    # unregister
#   .\scripts\idx-watchdog-task.ps1 -Status    # state + last run
# It runs `idx watchdog` (blackheart_ingest/idx/watchdog.py): job heartbeats vs the deadlines the desk depends on; a breach is a
# critical alert pushed at once. Separate from the scheduler task on purpose: a hung scheduler cannot silence its own watchdog.
param([switch]$Remove, [switch]$Status)

$name = "Blackheart IDX watchdog"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "logs\idx"
New-Item -ItemType Directory -Force $logDir | Out-Null
$wrapper = Join-Path $root "scripts\idx.ps1"
$log = Join-Path $logDir "watchdog.log"

if ($Status) {
    Get-ScheduledTask -TaskName $name -ErrorAction Stop | Format-List TaskName, State
    Get-ScheduledTaskInfo -TaskName $name | Format-List LastRunTime, LastTaskResult, NextRunTime
    exit 0
}
if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    "removed '$name'"
    exit 0
}

$cmd = "& '$wrapper' watchdog *>> '$log'"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$cmd`"" `
    -WorkingDirectory $root
# every 10 minutes forever: a daily trigger carrying a 23h50m repetition (the same construction as the scheduler's watchdog)
$t = New-ScheduledTaskTrigger -Daily -At 00:05
$t.Repetition = (New-ScheduledTaskTrigger -Once -At 00:05 -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Hours 23 -Minutes 50)).Repetition
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $t -Settings $settings -Force | Out-Null
"registered '$name' (every 10 minutes; log $log)"
