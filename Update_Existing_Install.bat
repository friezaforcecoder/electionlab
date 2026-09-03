@echo off
setlocal
cd /d "%~dp0"
echo ElectionLab 0.12 existing-install updater
echo.
echo This updates app/runtime files only.
echo It skips ElectionLabData, .venv, portable_config.json, saves, Vault data, portraits and logs.
echo.
set /p TARGET=Existing ElectionLab folder: 
if "%TARGET%"=="" (
  echo No target selected.
  pause
  exit /b 1
)
if not exist "%TARGET%" (
  echo Target folder does not exist.
  pause
  exit /b 1
)
if not exist "%TARGET%\electionlab" (
  echo Target does not look like an ElectionLab install.
  pause
  exit /b 1
)
echo.
echo Updating "%TARGET%"...
robocopy "%~dp0" "%TARGET%" /E /XD .git .venv ElectionLabData KnowledgeVault Campaigns Saves ResearchCache Models DataPacks Extensions Exports Logs __pycache__ .pip-cache .install-temp dist build /XF portable_config.json *.pyc *.pyo *.log *.db *.sqlite *.sqlite3 *.zip *.7z *.msi *.exe
set RC=%ERRORLEVEL%
if %RC% GEQ 8 (
  echo.
  echo Update failed with robocopy code %RC%.
  pause
  exit /b %RC%
)
echo.
echo Update complete. Launch with Run_ElectionLab_NoConsole.vbs or Run_ElectionLab.bat.
pause
exit /b 0
