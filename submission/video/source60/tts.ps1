# Local text-to-speech for the WAKALA video narration (Windows System.Speech; no network service).
# Writes one 44.1 kHz mono WAV per narration line: tts\<scene>_<n>.wav
# Usage: powershell -ExecutionPolicy Bypass -File tts.ps1
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$n = Get-Content (Join-Path $here "narration.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$out = Join-Path $here "tts"
New-Item -ItemType Directory -Force $out | Out-Null
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice("Microsoft Zira Desktop")
$s.Rate = 0
$s.Volume = 100
foreach ($scene in $n.scenes) {
  $i = 0
  $s.Rate = $(if ($null -ne $scene.rate) { [int]$scene.rate } else { 0 })
  foreach ($line in $scene.lines) {
    $i++
    # pronunciation hint only for speech; subtitles keep the real spelling
    $spoken = $line -replace "WAKALA", "Wakaala"
    $file = Join-Path $out ("{0}_{1}.wav" -f $scene.id, $i)
    $s.SetOutputToWaveFile($file, $fmt)
    $s.Speak($spoken)
    $s.SetOutputToNull()
  }
}
$s.Dispose()
Write-Output ("voice: Microsoft Zira Desktop, per-scene rate (narration.json); files: " + (Get-ChildItem $out -Filter *.wav).Count)
