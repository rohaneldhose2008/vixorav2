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

echo [*] Starting Ngrok Secure Tunnel on port 8001...
start "Vixora Ngrok Tunnel" /D "d:\vixora version 2" .\ngrok.exe http 8001

echo.
echo ====================================================================
echo             VIXORA V2 has been launched successfully!
echo ====================================================================
echo.
echo 1. Wait 3-5 seconds for services to initialize.
echo 2. The backend will automatically detect your Ngrok URL on port 8001.
echo 3. Open http://localhost:8001/ in your browser for the Admin Portal.
echo 4. Open http://localhost:8001/display for the TV display.
echo 5. To close VIXORA, run stop.bat or close the open command windows.
echo ====================================================================
pause
