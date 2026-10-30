@echo off
title MEI E2 Analytics & Escalation Dashboard
echo ============================================================
echo   MEI E2 ESCALATION LOGGING & SHAPE CORRECTION DASHBOARD
echo ============================================================
echo   * Starting Dashboard Server on Port 5000...
echo   * Open Browser: http://127.0.0.1:5000
echo ============================================================
echo.

cd /d "%~dp0"

REM Use venv python if available, otherwise default python
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe app.py
) else (
    python app.py
)

pause
