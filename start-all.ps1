# ai-live 一键启动：语音服务(8770) + 摄像头/麦克风采集 + 打开通话页
#
# 用法（三选一）：
#   双击  启动.bat                ← 最省事，窗口会停住让你看结果
#   pwsh -File start-all.ps1
#   powershell -EP Bypass -File start-all.ps1
#
# 参数：  -Force      内存不足也直接启动（不问）
#         -NoBrowser  不起来要浏览器
#
# 注意：服务由「任务计划程序」的 ai-live-watchdog 托管启动
# （Start-Process 起的子进程会跟着这个窗口一起死，所以统一走计划任务）

param(
  [switch]$Force,
  [switch]$NoBrowser
)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8770
$task = "ai-live-watchdog"
$flag = Join-Path $here "svc\paused.flag"

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }
function Need-Admin-Hint {
  Say ""
  Say "  [!] 操作计划任务需要一个有权限的 PowerShell。" -ForegroundColor Red
  Say "      右键 启动.bat → 以管理员身份运行。" -ForegroundColor DarkYellow
}

Say ""
Say "  ai-live 启动中" Cyan

# ---------------------------------------------------------------- 0) 前置检查
$shell = (Get-Command powershell.exe -ErrorAction SilentlyContinue)
if (-not (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue)) {
  Say "  [!] 这个 PowerShell 没有 ScheduledTasks 模块（可能是 PowerShell 2.0）" Red
  Say "      用 powershell.exe（5.1）或 pwsh 7 跑，别用旧版。" DarkYellow
  exit 1
}

# 内存体检：这台机器 15.2G，TTS 一加载就吃掉 4G 上下
$freeGB = 0.0
try {
  $freeGB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
} catch {
  $freeGB = -1
}
if ($freeGB -ge 0 -and $freeGB -lt 2.5 -and -not $Force) {
  Say ""
  Say "  [!] 现在只剩 $freeGB GB 物理内存，TTS 加载很可能把整机拖崩。" Red
  Say "      建议先关掉 ComfyUI / OBS / 微信视频。" DarkYellow
  Say ""
  $go = 'y'
  $interactive = $true
  try { $interactive = [Environment]::UserInteractive -and ($Host.Name -eq 'ConsoleHost') } catch { }
  try { if ([Console]::IsInputRedirected) { $interactive = $false } } catch { }
  if ($interactive) {
    try {
      $go = Read-Host "  还是继续吗？(y/N)"
    } catch {
      $go = 'y'   # 读不到输入就当作继续
    }
  } else {
    Say "  非交互运行（管道/脚本调用），按继续处理；要停下请 Ctrl+C。" DarkGray
    $go = 'y'
  }
  if ($go -ne 'y' -and $go -ne 'Y') {
    Say "  已取消。要强制启动：  .\start-all.ps1 -Force" DarkGray
    exit 1
  }
} elseif ($freeGB -ge 0) {
  Say "  空闲内存 $freeGB GB" DarkGray
}

# ---------------------------------------------------------------- 1) 恢复看门狗
try {
  if (Test-Path $flag) { Remove-Item $flag -Force -ErrorAction Stop }
} catch {
  Say "  [!] 删不掉 $flag ：$($_.Exception.Message)" Red
  Need-Admin-Hint
  exit 1
}

$t = $null
try { $t = Get-ScheduledTask -TaskName $task -ErrorAction Stop } catch { $t = $null }
if (-not $t) {
  Say "  [1/4] 找不到计划任务 $task" Red
  Say "        见 README-通话.md「装成计划任务」一节，或跑一次 install-task.ps1" DarkGray
  exit 1
}

try {
  Enable-ScheduledTask -TaskName $task -ErrorAction Stop | Out-Null
  Say "  [1/4] 看门狗已恢复" Green
} catch {
  Say "  [1/4] 启用计划任务失败：$($_.Exception.Message)" Red
  Need-Admin-Hint
  exit 1
}

# ---------------------------------------------------------------- 2) 立刻跑一次
try {
  Start-ScheduledTask -TaskName $task -ErrorAction Stop
  Say "  [2/4] 已让看门狗拉起服务（模型加载约 50-60 秒）" Yellow
} catch {
  Say "  [2/4] 触发计划任务失败：$($_.Exception.Message)" Red
  Need-Admin-Hint
  exit 1
}

# ---------------------------------------------------------------- 3) 等服务就绪
Write-Host "  [3/4] 等语音服务" -NoNewline -ForegroundColor Yellow
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
  try {
    $j = (Invoke-WebRequest "http://127.0.0.1:$port/api/status" -UseBasicParsing -TimeoutSec 2).Content
    if ($j -match '"ready":\s*true') { $ok = $true; break }
  } catch { }
  Start-Sleep -Seconds 2
  if ($i % 5 -eq 0) { Write-Host "." -NoNewline -ForegroundColor DarkGray }
}
Write-Host ""

if (-not $ok) {
  Say "  [3/4] 3 分钟内没就绪" Red
  Say "        日志： $here\voice_server.err.log" DarkGray
  Say "        常见原因：显存被占 / 内存不足 / torch 在 c10.dll 里崩了" DarkGray
  $tail = Join-Path $here "voice_server.err.log"
  if (Test-Path $tail) {
    Say "        ---- 最后几行 ----" DarkGray
    Get-Content $tail -Tail 8 -Encoding UTF8 | ForEach-Object { Say "        $_" DarkGray }
  }
} else {
  Say "  [3/4] 就绪" Green
}

# ---------------------------------------------------------------- 4) 开页面
if (-not $NoBrowser) {
  try { Start-Process "http://127.0.0.1:$port/" } catch { }
  Say "  [4/4] 已打开 http://127.0.0.1:$port/  —— 点「接通」开始" Green
} else {
  Say "  [4/4] 跳过打开浏览器：http://127.0.0.1:$port/" Green
}

Say ""
Say "  停： pwsh -File stop-all.ps1   （或双击 停止.bat）" DarkGray
Say ""
