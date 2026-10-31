cd /d "%~dp0"
start "" "D:\sakana-py\python.exe" "%~dp0server.py"
timeout /t 2 >nul
start "" "http://127.0.0.1:8772/"
