@echo off
cd /d "%~dp0"
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_measurement_system.ps1"
if errorlevel 1 pause
