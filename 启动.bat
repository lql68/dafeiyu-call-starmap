@echo off
setlocal
cd /d "%~dp0"
echo.
echo   ===== ai-live START =====
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" %*
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo   [exit %RC%]  see the red lines above
) else (
  echo   Done. You can close this window.
)
echo.
pause