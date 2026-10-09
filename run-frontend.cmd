@echo off
REM Keep the SurrealVideo frontend (Vite dev server) running, detached from any shell.
REM Logs go to frontend\.vite-dev.log
cd /d "%~dp0frontend"
:loop
if not exist "node_modules" call npm install
echo [%date% %time%] starting vite >> ".vite-dev.log"
call npm run dev >> ".vite-dev.log" 2>&1
echo [%date% %time%] vite exited, restarting in 5s >> ".vite-dev.log"
timeout /t 5 /nobreak >nul
goto loop
