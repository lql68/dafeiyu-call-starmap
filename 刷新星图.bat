@echo off
chcp 65001 >nul 2>&1
echo.
echo  == Refresh memory star map ==
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0svc\refresh-graph.ps1"
echo.
echo  Done. Reopen starmap.html to see the new data.
echo  Log: %~dp0svc\refresh-graph.log
echo.
pause
