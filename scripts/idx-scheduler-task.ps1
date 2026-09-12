# Register (or remove) the IDX data-plane scheduler as a Windows scheduled task.
#   .\scripts\idx-scheduler-task.ps1            # register: runs at logon, hidden, restarts if it dies
#   .\scripts\idx-scheduler-task.ps1 -Remove    # unregister
#   .\scripts\idx-scheduler-task.ps1 -Status    # show state + last run
# The task runs scripts\idx.ps1 run-scheduler (APScheduler, Asia/Jakarta); the scheduler writes logs\idx\scheduler.log itself.
param([switch]$Remove, [switch]$Status)

$name = "Blackheart IDX scheduler"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "logs\idx"
New-Item -ItemType Directory -Force $logDir | Out-Null
$wrapper = Join-Path $root "scripts\idx.ps1"
$log = Join-Path $logDir "scheduler.log"

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

$cmd = "& '$wrapper' run-scheduler"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$cmd`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $name
"registered + started '$name' (at logon, hidden). log: $log"
"remove with: .\scripts\idx-scheduler-task.ps1 -Remove"
