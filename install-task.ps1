# 装/修 计划任务 ai-live-watchdog —— 换机器或任务被删了就跑一次这个
# 不需要管理员（注册当前用户的任务即可）
#
# 用法：  powershell -EP Bypass -File install-task.ps1

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$wd = Join-Path $here "svc\watchdog.ps1"
$task = "ai-live-watchdog"

Write-Host ""
Write-Host "  装计划任务：$task" -ForegroundColor Cyan

if (-not (Test-Path $wd)) {
  Write-Host "  [!] 找不到 $wd" -ForegroundColor Red
  exit 1
}

$act = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $wd)
$trg = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes 2)
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $task -Action $act -Trigger $trg -Settings $set -Force | Out-Null

# 顺手修一下 .ps1 的编码：PowerShell 5.1 只认 UTF-8 BOM，否则中文变乱码直接语法错
$bom = New-Object System.Text.UTF8Encoding($true)
foreach ($f in @($wd, (Join-Path $here "start-all.ps1"), (Join-Path $here "stop-all.ps1"))) {
  if (Test-Path $f) {
    $bytes = [System.IO.File]::ReadAllBytes($f)
    if (-not ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191)) {
      $text = [System.IO.File]::ReadAllText($f, [System.Text.Encoding]::UTF8)
      [System.IO.File]::WriteAllText($f, $text, $bom)
      Write-Host "  补 BOM： $([System.IO.Path]::GetFileName($f))" -ForegroundColor DarkYellow
    }
  }
}

Write-Host "  完成。跑一次看效果：" -ForegroundColor Green
Write-Host "      Start-ScheduledTask -TaskName $task" -ForegroundColor DarkGray
Write-Host "  或直接双击 启动.bat" -ForegroundColor Green
Write-Host ""
