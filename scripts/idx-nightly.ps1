# Unattended nightly run of the IDX desk by Claude (agent-desk plan, phase 3).
# Registered as the Windows task "Blackheart IDX nightly" (Mon-Fri 20:45 WIB, after the ingest daily chain) by
#   scripts\idx-nightly.ps1 -Register
# Runs `claude -p` from C:\Project with the idx-desk MCP server (from .mcp.json), the skill's ritual as the prompt, a dollar
# budget, and no session persistence. Everything the agent does is journaled server-side (idx.decision) and guarded there
# (two-key, halt, validate); the log of the run itself goes to C:\Project\logs\idx\nightly\<date>.log.
#
#   scripts\idx-nightly.ps1               run now (what the task does)
#   scripts\idx-nightly.ps1 -Smoke        plumbing check only: one cheap tool call, $1 budget
#   scripts\idx-nightly.ps1 -Register     (re)create the scheduled task
param(
    [switch]$Register,
    [switch]$Smoke,
    [string]$Model = "claude-opus-5",
    [double]$BudgetUsd = 5
)
$ErrorActionPreference = "Stop"
$root = "C:\Project"
$PSDefaultParameterValues["Out-File:Encoding"] = "utf8"
$PSDefaultParameterValues["Tee-Object:Encoding"] = "utf8"
$logDir = Join-Path $root "logs\idx\nightly"
New-Item -ItemType Directory -Force $logDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd"
$log = Join-Path $logDir "$stamp$(if ($Smoke) { '-smoke' }).log"

if ($Register) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $root `
        -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\scripts\idx-nightly.ps1`""
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At "20:45"
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
    Register-ScheduledTask -TaskName "Blackheart IDX nightly" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host "registered 'Blackheart IDX nightly' (Mon-Fri 20:45 local = WIB on this machine)"
    exit 0
}

# 1. the ingest API must be up (the scheduler task does not start it)
$listening = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Get-Content (Join-Path $root "blackheart-ingest\idx-local.env") | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object {
        $k, $v = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($k, $v, 'Process')
    }
    Start-Process -FilePath (Join-Path $root "blackheart-ingest\.venv\Scripts\python.exe") -WorkingDirectory (Join-Path $root "blackheart-ingest") `
        -ArgumentList "-m", "uvicorn", "blackheart_ingest.workers.server:app", "--host", "127.0.0.1", "--port", "8001" -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 8
    "$(Get-Date -Format s) started the ingest API (was not listening)" | Tee-Object -FilePath $log -Append
}

# 2. the prompt: the ritual lives in the skill; the runner only says "tonight, unattended". It goes to Claude on stdin,
#    not as an argument: PowerShell -> claude.cmd -> node re-parses quotes and backticks, and a prompt with either
#    swallowed the flags after it on the first real run (2026-09-17). Single-quoted here-strings: nothing is expanded.
if ($Smoke) {
    $prompt = @'
Plumbing check: call the idx-desk MCP tool named ops (runs_limit 1) and reply with exactly one line:
last_bar_date=<value> open_alerts=<count>. If the tool is refused or unavailable, reply exactly: TOOL_REFUSED. Do nothing else.
'@
    $BudgetUsd = 1
} else {
    $prompt = @'
Run tonight's IDX desk ritual, unattended. Read C:\Project\.claude\skills\idx-desk\SKILL.md first and follow its rules and
its Nightly ritual section exactly, with the idx-desk MCP tools only. No one will answer questions: when a rule says stop,
stop and report. If an idx-desk tool is refused, stop and report TOOL_REFUSED (rule 8) - do not work around it.
Finish with the report table from rule 7, then send the same summary (max 15 lines) with the notify tool.
'@
}
$system = "Unattended nightly run started by a scheduled task at $(Get-Date -Format s). There is no operator at the keyboard: never ask, decide within the skill rules or stop. Do not start background work, do not write files or memory. Keep tool calls purposeful; the run has a $BudgetUsd dollar budget."
$promptFile = "$log.prompt.txt"
[System.IO.File]::WriteAllText($promptFile, $prompt, (New-Object System.Text.UTF8Encoding $false))

# 3. run Claude headless from the workspace root so .mcp.json and the skill resolve. Only the desk tools (+ Read for the
#    skill file, Skill) are allowed; every editing/shell/web tool is denied so a refused tool cannot be routed around.
#    PowerShell 5.1 turns a native command's stderr into error records, so stderr goes to its own file and the preference
#    is relaxed around the call.
Set-Location $root
"$(Get-Date -Format s) nightly start model=$Model budget=$BudgetUsd smoke=$Smoke" | Tee-Object -FilePath $log -Append
$env:CLAUDECODE = $null                                       # not a nested interactive session
$cliArgs = @(
    "-p",
    "--model", $Model,
    "--mcp-config", (Join-Path $root ".mcp.json"), "--strict-mcp-config",
    "--allowedTools", "mcp__idx-desk", "Read", "Skill",
    "--disallowedTools", "Bash", "PowerShell", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch", "Agent",
    "--append-system-prompt", $system,
    "--max-budget-usd", "$BudgetUsd",
    "--no-session-persistence",
    "--output-format", "text"
)
$ErrorActionPreference = "Continue"
Get-Content $promptFile -Raw -Encoding UTF8 | & claude @cliArgs 2> "$log.stderr" | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Remove-Item $promptFile -Force -ErrorAction SilentlyContinue
if (Test-Path "$log.stderr") {
    # drop PowerShell's error-record wrapping and Claude Code's permission-rule lint (workspace settings.json, harmless here)
    $err = (Get-Content "$log.stderr" | Where-Object { $_ -and $_ -notmatch '^\s*\+ ' -and $_ -notmatch 'CategoryInfo|FullyQualifiedErrorId|^At C:|Permission allow rule|file-editing tools|file-reading tools|approves them without a prompt|value you mean|^\s*tools\)\.\s*$' }) -join "`n"
    if ($err) { "stderr: $err" | Tee-Object -FilePath $log -Append }
    Remove-Item "$log.stderr" -Force
}
"$(Get-Date -Format s) nightly end exit=$code" | Tee-Object -FilePath $log -Append
exit $code
