@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo ElectionLab environment is not installed yet.
  echo Run Install_ElectionLab.bat first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "ElectionLab.pyw"
exit /b 0
