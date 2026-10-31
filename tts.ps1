# tts.ps1 - speak the AI line out loud (ASCII only, zero deps via SAPI)
#   .\tts.ps1 "树倒了，木材在手"
#   .\tts.ps1 -Text "..." -Voice "Microsoft Huihui Desktop" -Rate 2 -Volume 95
#   .\tts.ps1 -Text "..." -File out.wav    # render to wav instead of speaking
#
# Optional higher quality: pip install edge-tts
#   edge-tts --voice zh-CN-XiaoyiNeural --text "..." --write-media out.mp3
param(
  [Parameter(Position=0)][string]$Text = '',
  [string]$Voice = '',
  [int]$Rate = 0,
  [int]$Volume = 95,
  [string]$File = ''
)
$ErrorActionPreference = 'Stop'
if (-not $Text) { throw 'empty text' }

Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($Voice) {
  try { $s.SelectVoice($Voice) } catch { Write-Host "  [warn] voice not found: $Voice" }
} else {
  $zh = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'zh-*' } | Select-Object -First 1
  if ($zh) { $s.SelectVoice($zh.VoiceInfo.Name) }
}
$s.Rate = $Rate
$s.Volume = $Volume

if ($File) {
  $s.SetOutputToWaveFile($File)
  $s.Speak($Text)
  $s.SetOutputToNull()
  $s.Dispose()
  Write-Host "wrote $File"
} else {
  $s.Speak($Text)
  $s.Dispose()
  Write-Host "spoke: $Text"
}