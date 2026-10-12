@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.13 -m venv .venv 2>nul
  if errorlevel 1 py -3.12 -m venv .venv 2>nul
  if errorlevel 1 py -3 -m venv .venv 2>nul
  if errorlevel 1 (
    echo Please install Python 3.12 or 3.13 and retry.
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
echo.
echo Open http://127.0.0.1:8008 in your browser, keep this window open.
.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8008
pause
