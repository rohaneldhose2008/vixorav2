@echo off
title VIXORA V2 - Shutdown Manager
color 0C
cls
echo ====================================================================
echo             VIXORA V2 by NEXORA Creation - Shutdown Manager
echo ====================================================================
echo.
echo [*] Performing privacy wipe (deleting photos & database)...
.\backend\venv\Scripts\python.exe -c "import pathlib; [f.unlink() for f in pathlib.Path('backend/photos').iterdir() if f.is_file()] if pathlib.Path('backend/photos').exists() else None; [f.unlink() for f in pathlib.Path('backend/watch_folder').iterdir() if f.is_file() and f.suffix.lower() in ('.jpg','.jpeg','.png')] if pathlib.Path('backend/watch_folder').exists() else None; db_path = pathlib.Path('backend/vixora2.db'); db_path.exists() and db_path.unlink()" 2>nul
echo [*] Privacy wipe complete.

echo [*] Stopping secure tunnels (Cloudflare & Ngrok)...
taskkill /F /FI "WINDOWTITLE eq Vixora Ngrok Tunnel*" 2>nul
taskkill /F /FI "WINDOWTITLE eq Vixora Cloudflare Tunnel*" 2>nul
powershell -Command "Get-Process cloudflared, ngrok -ErrorAction SilentlyContinue | Stop-Process -Force" 2>nul
if exist "backend\cloudflared.log" del "backend\cloudflared.log"

echo [*] Stopping VIXORA V2 backend server...
taskkill /F /FI "WINDOWTITLE eq Vixora Backend*" 2>nul
powershell -Command "Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*d:\vixora version 2*' } | Stop-Process -Force" 2>nul

echo.
echo ====================================================================
echo  All VIXORA V2 services have been stopped and data has been wiped!
echo ====================================================================
echo.
pause
