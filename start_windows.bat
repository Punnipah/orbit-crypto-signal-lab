@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Orbit Crypto Signal Lab - Initializing...
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found. Please install Python 3.11 or 3.12 first.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1
if errorlevel 1 goto :failed
exit /b 0
:failed
echo Unable to start. Please check the error above.
pause
exit /b 1
