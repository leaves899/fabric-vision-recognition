@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYRUN=python"
where py >nul 2>nul
if not errorlevel 1 set "PYRUN=py -3"
%PYRUN% -c "from PIL import Image" >nul 2>nul
if errorlevel 1 (
  echo Missing Pillow or Python. In this repository run:
  echo    py -3 -m pip install Pillow
  echo or python -m pip install Pillow
  pause
  exit /b 1
)
echo Starting local yarn annotation, saving into this Git checkout...
%PYRUN% -m benchmark.manual_annotation serve --port 8765 --open
echo Local annotation service stopped.
pause
