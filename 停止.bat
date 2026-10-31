@echo off
setlocal
cd /d "%~dp0"
echo.
echo   ===== ai-live STOP =====
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-all.ps1" %*
echo.
pause