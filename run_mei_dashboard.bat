@echo off
title MEI E2 Escalation Logging Dashboard
echo ============================================================
echo  🚀 Starting MEI E2 Escalation Logging Dashboard Server...
echo ============================================================
echo  -> Open Browser: http://127.0.0.1:5000
echo ============================================================
cd /d "%~dp0"
python app.py
pause
