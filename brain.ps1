# brain.ps1 - the "AI plays the game" loop (ASCII only)
#   Screenshot (OBS) -> vision model -> action list -> sai.ps1 inject -> push line to panel
#
# Usage:
#   $env:AI_BASE = "https://api.openai.com/v1"     # any OpenAI-compatible endpoint
#   $env:AI_KEY  = "sk-..."                        # bearer token
#   $env:AI_MODEL= "gpt-4o-mini"                   # must accept image_url
#   .\brain.ps1                 # one decision round
#   .\brain.ps1 -Loop -Interval 6   # keep playing every 6s
param(
  [switch]$Loop,
  [int]$Interval = 6,
  [string]$Shot = 'D:\deepseek harness\galgame-stream\shots\now.png',
  [string]$Bridge = 'http://127.0.0.1:8765',
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$GS = 'D:\deepseek harness\galgame-stream'

$base  = $env:AI_BASE;  if (-not $base)  { $base  = 'https://api.openai.com/v1' }
$key   = $env:AI_KEY;   if (-not $key)   { throw 'set $env:AI_KEY first' }
$model = $env:AI_MODEL; if (-not $model) { $model = 'gpt-4o-mini' }

function Take-Shot {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $GS 'g.ps1') shot | Out-Null
  if (-not (Test-Path $Shot)) { throw 'screenshot failed' }
}

function Ask-Model([string]$imgPath) {
  $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($imgPath))
  $sys = @'
You are the brain of an AI streamer playing Terraria (Chinese stream). Look at the screenshot and pick the next few actions.
Reply with ONE json object, no markdown fence:
{"say":"<15 Chinese chars, what you say to chat>","actions":["key d 800","hold 860 545 2000"],"game":{"a":"<day>","b":"<biome>","c":"<hp>","last":"<what you just did>"}}
Action grammar (one per string):
  key <k> <ms>        hold a key, k in a-z 0-9 space enter esc tab shift ctrl alt up down left right
  tap <k>             tap a key
  hold <x> <y> <ms>   hold left mouse at logical pixel (screen is 1706x1066)
  click <x> <y>       click at logical pixel
Rules: stay safe (avoid falling into deep holes with low hp), prefer mining/chopping/building,
2-4 actions per turn, coordinates must be inside 40..1666 x 40..1026.
'@
  $body = @{
    model = $model
    temperature = 0.7
    max_tokens = 400
    messages = @(
      @{ role = 'system'; content = $sys },
      @{ role = 'user'; content = @(
          @{ type = 'text'; text = 'Screenshot of the current game frame. Decide the next actions.' },
          @{ type = 'image_url'; image_url = @{ url = "data:image/png;base64,$b64" } }
      )}
    )
  } | ConvertTo-Json -Depth 12

  $r = Invoke-RestMethod -Uri "$base/chat/completions" -Method Post `
        -Headers @{ Authorization = "Bearer $key" } `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 120
  return $r.choices[0].message.content
}

function Parse-Json([string]$txt) {
  $t = $txt.Trim()
  $t = $t -replace '(?s)^```(json)?', '' -replace '```$', ''
  $i = $t.IndexOf('{'); $j = $t.LastIndexOf('}')
  if ($i -ge 0 -and $j -gt $i) { $t = $t.Substring($i, $j - $i + 1) }
  return $t | ConvertFrom-Json
}

function Push-State($obj) {
  try {
    Invoke-RestMethod -Uri "$Bridge/push" -Method Post `
      -ContentType 'application/json; charset=utf-8' `
      -Body ([Text.Encoding]::UTF8.GetBytes(($obj | ConvertTo-Json -Depth 6))) -TimeoutSec 5 | Out-Null
  } catch { Write-Host "  [warn] bridge push failed: $($_.Exception.Message)" }
}

function Run-Actions($actions) {
  foreach ($a in $actions) {
    $parts = "$a".Trim() -split '\s+'
    if ($parts.Count -lt 2) { continue }
    $verb = $parts[0].ToLower()
    if ($verb -notin @('key','tap','hold','click','move')) { Write-Host "  skip: $a"; continue }
    Write-Host "  > $a"
    if ($DryRun) { continue }
    if ($verb -eq 'key' -or $verb -eq 'tap') {
      $ms = if ($parts.Count -ge 3) { $parts[2] } else { '120' }
      & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $GS 'sai.ps1') $verb $parts[1] $ms | Out-Null
    } else {
      $ms = if ($parts.Count -ge 4) { $parts[3] } elseif ($verb -eq 'hold') { '1500' } else { '90' }
      & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $GS 'sai.ps1') $verb $parts[1] $parts[2] $ms | Out-Null
    }
  }
}

function One-Round {
  Take-Shot
  $raw = Ask-Model $Shot
  Write-Host "[model] $raw"
  $dec = Parse-Json $raw
  if ($dec.say) {
    Write-Host "[say] $($dec.say)"
    Push-State @{ ai = @{ line = $dec.say; ts = '刚刚' } }
  }
  if ($dec.game) {
    Push-State @{ game = @{
      a = $dec.game.a; b = $dec.game.b; c = $dec.game.c; last = $dec.game.last
    } }
  }
  if ($dec.actions) { Run-Actions $dec.actions }
}

if ($Loop) {
  Write-Host "[brain] loop every ${Interval}s (ctrl-c to stop)"
  while ($true) {
    try { One-Round } catch { Write-Host "  [error] $($_.Exception.Message)" }
    Start-Sleep -Seconds $Interval
  }
} else {
  One-Round
}