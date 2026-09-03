@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\core_self_test.py
) else (
  python scripts\core_self_test.py
)
pause
