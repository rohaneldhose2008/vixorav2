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

echo [*] Starting Cloudflare Secure Tunnel on port 8001...
if exist "backend\cloudflared.log" del "backend\cloudflared.log"
start "Vixora Cloudflare Tunnel" /D "d:\vixora version 2" cmd /c ".\cloudflared.exe tunnel --url http://localhost:8001 > backend\cloudflared.log 2>&1"

echo.
echo ====================================================================
echo             VIXORA V2 has been launched successfully!
echo ====================================================================
echo.
echo 1. Wait 5-8 seconds for services to initialize.
echo 2. The backend will automatically detect your Cloudflare URL.
echo 3. Open http://localhost:8001/ in your browser for the Admin Portal.
echo 4. Open http://localhost:8001/display for the TV display.
echo 5. Scan the QR codes on display to download photos (no Vercel needed!).
echo 6. To close VIXORA, run stop.bat or close the open command windows.
echo ====================================================================
pause
