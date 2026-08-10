@echo off
title Feedback Loop - local launcher
set "ROOT=%~dp0"
echo.
echo   Starting the Feedback Loop on your computer...
echo   (two windows will open: the AI Brain + the Website)
echo.

rem The website runs in PRODUCTION mode (fast, no per-click compiling).
rem First launch after a code update builds once (~1 min); after that, startup is instant.
if not exist "%ROOT%web\.next\BUILD_ID" (
  echo   First run after an update - building the website once, please wait ~1 minute...
  pushd "%ROOT%web"
  call npm run build
  popd
)

start "Feedback Worker (AI Brain) - port 8000" /d "%ROOT%ratings_module_build_kit" cmd /k .venv\Scripts\python.exe -m uvicorn service:app --port 8000
start "Feedback Website - port 3000" /d "%ROOT%web" cmd /k npm run start

echo   Give it about 10 seconds to warm up, then your browser opens...
timeout /t 10 >nul
start "" http://localhost:3000/login

echo.
echo   ------------------------------------------------------------
echo    Website:  http://localhost:3000
echo    Log in:   your IK email + password (email/password works locally;
echo              Google works on the live site - see docs\RUN_LOCAL.md)
echo   ------------------------------------------------------------
echo.
echo   After pulling NEW code: delete the folder  web\.next  once so the
echo   launcher rebuilds, or run "npm run build" inside web\ yourself.
echo.
echo   To STOP: close the two black windows (Worker + Website).
echo.
pause
