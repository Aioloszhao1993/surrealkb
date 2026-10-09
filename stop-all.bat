@echo off
title Stop SurrealVideo
echo =======================================
echo   Stop SurrealVideo (backend/frontend/db)
echo =======================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-all.ps1"
echo.
pause
