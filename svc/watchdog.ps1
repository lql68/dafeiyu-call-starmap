# ai-live 看门狗：语音服务(8770) + 摄像头采集，谁死了拉谁
# 由「任务计划程序」的 ai-live-watchdog 每 2 分钟跑一次，所以 DSH 崩了也不影响它
$ErrorActionPreference = 'SilentlyContinue'
$here = "D:\deepseek harness\ai-live"
$log  = Join-Path $here "svc\watchdog.log"
$flag = Join-Path $here "svc\paused.flag"

# stop-all.ps1 会停用这个任务并留下 paused.flag，见到就直接退出
if (Test-Path $flag) { exit 0 }

function Write-Log($m) {
  $line = "{0}  {1}" -f (Get-Date).ToString("MM-dd HH:mm:ss"), $m
  Add-Content -Path $log -Value $line -Encoding utf8
}

# ---------- 语音服务 ----------
$voiceUp = [bool](Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue)
if (-not $voiceUp) {
  $env:PYTHONIOENCODING = "utf-8"
  $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
  $env:AI_LIVE_NUM_GPU = "16"
  Start-Process -FilePath "D:\index-tts\.venv\Scripts\python.exe" `
    -ArgumentList "`"$here\voice_server.py`" --port 8770" `
    -WorkingDirectory $here -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $here "voice_server.log") `
    -RedirectStandardError  (Join-Path $here "voice_server.err.log")
  Write-Log "起 voice_server"
}

# ---------- 摄像头 / 麦克风采集 ----------
$cam = Get-CimInstance Win32_Process |
       Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*ai-live\vision\vision.py*' }
if (-not $cam) {
  Start-Process -FilePath "D:\sakana-py\python.exe" `
    -ArgumentList "`"$here\vision\vision.py`" --snap-every 5" `
    -WorkingDirectory (Join-Path $here "vision") -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $here "vision\vision.out.log") `
    -RedirectStandardError  (Join-Path $here "vision\vision.err.log")
  Write-Log "起 vision.py"
}