@echo off
title Feedback Loop - local launcher
set "ROOT=%~dp0"
echo.
echo   Starting the Feedback Loop on your computer...
echo   (two windows will open: the AI Brain + the Website)
echo.

start "Feedback Worker (AI Brain) - port 8000" /d "%ROOT%ratings_module_build_kit" cmd /k .venv\Scripts\python.exe -m uvicorn service:app --port 8000
start "Feedback Website - port 3000" /d "%ROOT%web" cmd /k npm run dev

echo   Give it about 15 seconds to warm up, then your browser opens...
timeout /t 15 >nul
start "" http://localhost:3000/login

echo.
echo   ------------------------------------------------------------
echo    Website:  http://localhost:3000
echo    Log in:   your IK email + password (email/password works locally;
echo              Google works on the live site - see docs\RUN_LOCAL.md)
echo   ------------------------------------------------------------
echo.
echo   To STOP: close the two black windows (Worker + Website).
echo.
pause
