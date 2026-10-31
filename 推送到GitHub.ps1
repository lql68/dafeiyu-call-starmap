# 把 ai-live（通话页 + 记忆星图）推到 GitHub
# 前置：Clash/代理开着（这台机器访问 GitHub 必须走代理）
# 用法：右键 → 使用 PowerShell 运行；或在终端里 .\推送到GitHub.ps1

$ErrorActionPreference = 'Continue'
$gh  = "D:\AIGC\素材库\_tools\gh\bin\gh.exe"
$dir = "D:\deepseek harness\ai-live"
Set-Location $dir

Write-Host "`n=== 1/4 检查网络 ===" -ForegroundColor Cyan
$proxy = $null
foreach ($p in 7897, 7890, 10809, 1080) {
    if ((Test-NetConnection 127.0.0.1 -Port $p -WarningAction SilentlyContinue).TcpTestSucceeded) {
        $proxy = "http://127.0.0.1:$p"; break
    }
}
if (-not $proxy) {
    Write-Host "  没有代理端口在监听（7897 / 7890 / 10809 / 1080 都关了）" -ForegroundColor Red
    Write-Host "  先把 Clash / v2ray 打开，再跑一次这个脚本。" -ForegroundColor Yellow
    Read-Host "`n按回车退出"
    exit 1
}
$env:HTTPS_PROXY = $proxy
$env:HTTP_PROXY  = $proxy
Write-Host "  代理：$proxy" -ForegroundColor Green

try {
    $r = Invoke-WebRequest "https://api.github.com" -UseBasicParsing -TimeoutSec 12 `
         -Headers @{ 'User-Agent' = 'gh-script' }
    Write-Host "  api.github.com 可达（$($r.StatusCode)）" -ForegroundColor Green
} catch {
    Write-Host "  连不上 api.github.com：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  代理开着但没走通，检查 Clash 的规则模式。" -ForegroundColor Yellow
    Read-Host "`n按回车退出"
    exit 1
}

Write-Host "`n=== 2/4 检查 gh 登录 ===" -ForegroundColor Cyan
& $gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  还没登录，走浏览器授权（会给你一个 8 位码）" -ForegroundColor Yellow
    & $gh auth login --hostname github.com --git-protocol https --web --skip-ssh-key
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  登录没成功。" -ForegroundColor Red
        Read-Host "`n按回车退出"
        exit 1
    }
}
$who = (& $gh api user --jq .login 2>&1)
Write-Host "  已登录：$who" -ForegroundColor Green

Write-Host "`n=== 3/4 仓库 ===" -ForegroundColor Cyan
$name = "dafeiyu-call-starmap"
$exist = & $gh repo view "$who/$name" --json name 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  创建仓库 $who/$name（private）" -ForegroundColor Yellow
    & $gh repo create $name --private --source=. --remote=origin `
        --description "本地跑的虚拟形象视频通话页 + 记忆星图（Live2D / TTS / MediaPipe / 力导向星图）"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  创建失败（可能是同名仓库已存在，或 token 没 repo 权限）" -ForegroundColor Red
        Read-Host "`n按回车退出"
        exit 1
    }
} else {
    Write-Host "  仓库已存在，直接推" -ForegroundColor Green
    if (-not (& git remote)) { & git remote add origin "https://github.com/$who/$name.git" }
}

Write-Host "`n=== 4/4 推送 ===" -ForegroundColor Cyan
& git -c http.proxy=$proxy push -u origin master 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n完成：https://github.com/$who/$name" -ForegroundColor Green
    Start-Process "https://github.com/$who/$name"
} else {
    Write-Host "`n推送失败，看上面的报错。" -ForegroundColor Red
}
Read-Host "`n按回车关闭"
