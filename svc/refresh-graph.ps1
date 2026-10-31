# 每小时把 livingmemory 的最新图谱重新导一遍，并内联进 starmap.html
# 由计划任务 starmap-refresh 调用；也可以双击 刷新星图.bat 手动跑
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $PSScriptRoot          # svc 的上一级 = ai-live
$py   = 'D:\sakana-py\python.exe'
$log  = Join-Path $PSScriptRoot 'refresh-graph.log'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

function Note($msg) {
    Add-Content -Path $log -Value $msg -Encoding utf8
}

try {
    $a = & $py (Join-Path $here 'gen_memory_graph.py') 2>&1 | Out-String
    $b = & $py (Join-Path $here 'inline_graph.py')    2>&1 | Out-String
    Note "[$stamp] OK"
    Note $a.Trim()
    Note $b.Trim()
} catch {
    Note "[$stamp] FAIL  $($_.Exception.Message)"
}

# 日志只留最近 400 行，别无限长
if (Test-Path $log) {
    $lines = Get-Content $log -Encoding utf8
    if ($lines.Count -gt 400) {
        $lines | Select-Object -Last 400 | Set-Content $log -Encoding utf8
    }
}
