@echo off
setlocal
echo ElectionLab - Ollama Model Storage
echo.
set /p MODELROOT=Enter the folder where Ollama models should live: 
if "%MODELROOT%"=="" exit /b 1
if not exist "%MODELROOT%" mkdir "%MODELROOT%"
setx OLLAMA_MODELS "%MODELROOT%"
echo.
echo OLLAMA_MODELS is now set for your Windows account.
echo Fully quit and restart Ollama before downloading/pulling models.
pause
