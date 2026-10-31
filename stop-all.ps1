# 停掉 ai-live 的语音服务与采集
# 关键：先把看门狗计划任务停掉，否则它 2 分钟内会把服务拉回来 —— 这就是"关不掉"的原因
$ErrorActionPreference = 'SilentlyContinue'
$here = "D:\deepseek harness\ai-live"
$flag = Join-Path $here "svc\paused.flag"

Write-Host ""

# 1) 停看门狗
$t = Get-ScheduledTask -TaskName "ai-live-watchdog"
if ($t) {
  Stop-ScheduledTask   -TaskName "ai-live-watchdog"
  Disable-ScheduledTask -TaskName "ai-live-watchdog" | Out-Null
  Write-Host "  [1/3] 看门狗已停用（不会再把服务拉回来）" -ForegroundColor Yellow
} else {
  Write-Host "  [1/3] 没有看门狗任务" -ForegroundColor DarkGray
}

# 2) 立个暂停标记（万一计划任务被别的途径触发也会自己退出）
New-Item -ItemType File -Path $flag -Force | Out-Null

# 3) 杀进程
$done = @()
foreach ($pat in @("*ai-live\voice_server.py*", "*ai-live\vision\vision.py*")) {
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -like $pat } |
    ForEach-Object {
      Stop-Process -Id $_.ProcessId -Force
      $done += "$($_.Name) <- $($_.CommandLine.Substring(0,[Math]::Min(48,$_.CommandLine.Length)))"
    }
}

# 兜底：8770 还被占着就按端口杀（防止是 pythonw / 路径不同没匹配上）
$conn = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
  foreach ($pid_ in ($conn.OwningProcess | Select-Object -Unique)) {
    $pr = Get-Process -Id $pid_ -ErrorAction SilentlyContinue
    if ($pr -and $pr.ProcessName -like 'python*') {
      Stop-Process -Id $pid_ -Force
      $done += "pid $pid_ (占用 8770)"
    }
  }
}

Write-Host "  [2/3] 关掉 $($done.Count) 个进程" -ForegroundColor Yellow
$done | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }

# 4) 复核
Start-Sleep -Seconds 1
$still = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue
$cam   = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*vision.py*' })
if ($still) { Write-Host "  [3/3] 8770 还被占用，它可能不是 python —— 自己看一眼" -ForegroundColor Red }
else        { Write-Host "  [3/3] 8770 已释放，摄像头/麦克风已松开" -ForegroundColor Green }

Write-Host ""
Write-Host "  重新开：pwsh -File start-all.ps1" -ForegroundColor DarkGray
Write-Host ""