@echo off
REM Forza Horizon 5 Telemetry GUI - double-click launcher.
REM Opens a single-window app (status / sessions / cars tabs) and auto-starts
REM the recorder. To hide this console, replace 'python' with 'pythonw'.

chcp 65001 >nul
title Forza Telemetry GUI
cd /d "%~dp0"

python -m scripts.forza_telemetry.gui --auto-start

REM Only pause on error - clean GUI close exits 0 and the console closes too.
if errorlevel 1 (
    echo.
    echo Python exited with errorlevel %errorlevel%.
    pause
)
