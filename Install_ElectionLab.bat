@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo =====================================================
echo              ElectionLab Installer 0.12
echo =====================================================
echo.
echo App folder: %CD%
echo The Python environment will be created here:
echo %CD%\.venv
echo.

if /I "%~d0"=="C:" (
  echo WARNING: ElectionLab itself is currently on C:.
  echo For the smallest possible C: footprint, move/extract this whole folder
  echo to D:, F:, or another drive BEFORE installing.
  echo.
)

set "DEFAULTDATA=%CD%\ElectionLabData"
set /p DATAROOT=ElectionLab data root [default: %DEFAULTDATA%]: 
if "%DATAROOT%"=="" set "DATAROOT=%DEFAULTDATA%"
if not exist "%DATAROOT%" mkdir "%DATAROOT%"

rem Keep pip's large temporary/cache files beside ElectionLab during setup.
set "PIP_CACHE_DIR=%CD%\.pip-cache"
set "TEMP=%CD%\.install-temp"
set "TMP=%CD%\.install-temp"
if not exist "%TEMP%" mkdir "%TEMP%"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3 was not found. Install Python 3.11 or newer, then run this again.
    echo ElectionLab's own packages and large data will still stay in the folder you selected.
    pause
    exit /b 1
  )
  set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating project-local Python environment...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

echo Installing/updating ElectionLab dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

set "EL_DATAROOT=%DATAROOT%"
".venv\Scripts\python.exe" -c "import os,json,pathlib; p=pathlib.Path('portable_config.json'); d={}; d.update(json.loads(p.read_text(encoding='utf-8'))) if p.exists() else None; d['data_root']=os.environ['EL_DATAROOT']; p.write_text(json.dumps(d,indent=2),encoding='utf-8')"
if errorlevel 1 goto :fail

if exist "%CD%\.pip-cache" rmdir /s /q "%CD%\.pip-cache"
if exist "%CD%\.install-temp" rmdir /s /q "%CD%\.install-temp"

echo.
echo Installation complete.
echo Data root: %DATAROOT%
echo Run Run_ElectionLab_NoConsole.vbs to launch without a command window.
echo Run Run_ElectionLab.bat only if you need the compatibility launcher.
pause
exit /b 0

:fail
echo.
echo Installation failed. ElectionLab did not install itself system-wide.
echo Any partial project-local files can be removed by deleting this ElectionLab folder.
pause
exit /b 1
