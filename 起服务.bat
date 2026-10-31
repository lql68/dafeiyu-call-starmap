@echo off
rem Start both services WITHOUT touching the scheduled task watchdog.
rem The watchdog is disabled on purpose (it would relaunch things behind your back).
cd /d "%~dp0"

echo [1/2] voice_server.py   :8770
start "" "D:\index-tts\.venv\Scripts\pythonw.exe" "D:\deepseek harness\ai-live\voice_server.py" --port 8770

echo [2/2] vision.py   camera + mic + face
start "" "D:\sakana-py\pythonw.exe" "D:\deepseek harness\ai-live\vision\vision.py" --snap-every 5

echo.
echo TTS needs about 40s to warm up. Then open:
echo   http://127.0.0.1:8770/?auto=1
echo.
pause
