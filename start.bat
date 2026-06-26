@echo off
title VIXORA V2 - Startup Launcher
color 0B
cls
echo ====================================================================
echo             VIXORA V2 by NEXORA Creation - Startup Launcher
echo ====================================================================
echo.
echo [*] Starting VIXORA V2 Backend Server on port 8001...
set PORT=8001
start "Vixora Backend" /D "d:\vixora version 2\backend" .\venv\Scripts\python.exe run.py

echo.
echo ====================================================================
echo             VIXORA V2 has been launched successfully!
echo ====================================================================
echo.
echo 1. Wait 5-8 seconds for the backend to initialize.
echo 2. Open http://localhost:8001/ in your browser for the Admin Portal.
echo 3. Access the TV display and guest downloads directly on Vercel.
echo 4. To close VIXORA, run stop.bat or close the open command windows.
echo ====================================================================
pause
