# IDX data-plane CLI wrapper (local): loads blackheart-ingest\idx-local.env and runs the ingest venv.
#   .\scripts\idx.ps1 migrate | status | universe | daily --date D | index --date D | backfill --from D [--to D] [--index] | replay ...
$root = Split-Path -Parent $PSScriptRoot
Get-Content (Join-Path $root "blackheart-ingest\idx-local.env") | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)=(.*)$') { Set-Item -Path ("Env:" + $Matches[1]) -Value $Matches[2] }
}
$env:PYTHONIOENCODING = "utf-8"
Set-Location (Join-Path $root "blackheart-ingest")
& .\.venv\Scripts\python.exe -m blackheart_ingest.idx.cli @args
exit $LASTEXITCODE
