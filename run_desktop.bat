@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
  "%SCRIPT_DIR%.venv\Scripts\python.exe" "%SCRIPT_DIR%desktop_launcher.py" %*
  exit /b %errorlevel%
)

py -3 "%SCRIPT_DIR%desktop_launcher.py" %*
exit /b %errorlevel%
