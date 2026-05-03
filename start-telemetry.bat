@echo off
REM Forza Horizon 5 Telemetry Recorder - double-click launcher
REM Press Ctrl+C to stop, or just close the window.

chcp 65001 >nul
title Forza Telemetry Recorder
cd /d "%~dp0"

python -m scripts.forza_telemetry --verbose

echo.
pause
