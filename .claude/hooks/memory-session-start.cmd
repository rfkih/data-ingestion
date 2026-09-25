@echo off
REM SessionStart: remind the session that long-term memory is searchable, and print the few lines it should know.
REM Degrades silently when the tool or a python is missing, so it can never block a session from starting.
setlocal
set MEM=%USERPROFILE%\.claude\tools\mem.py
if not exist "%MEM%" exit /b 0
set PY=C:\Project\blackheart-ingest\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" "%MEM%" brief -k 3 2>nul
exit /b 0
