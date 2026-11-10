# Intelligibility check: transcribes each narration clip with the local Windows speech recognizer (dictation grammar)
# and reports word overlap with the script. Output: build\speech_check.json
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$n = Get-Content (Join-Path $here "narration.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$results = @()
foreach ($scene in $n.scenes) {
  $i = 0
  foreach ($line in $scene.lines) {
    $i++
    $wav = Join-Path $here ("tts\{0}_{1}.wav" -f $scene.id, $i)
    $r = New-Object System.Speech.Recognition.SpeechRecognitionEngine((New-Object System.Globalization.CultureInfo("en-US")))
    $r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
    $r.SetInputToWaveFile($wav)
    $heard = @()
    while ($true) {
      try { $res = $r.Recognize() } catch { break }  # input stream ended
      if ($null -eq $res) { break }; $heard += $res.Text
    }
    $r.Dispose()
    $text = ($heard -join " ")
    $want = ($line.ToLower() -replace "[^a-z' ]", " " -split "\s+") | Where-Object { $_ -ne "" }
    $got = ($text.ToLower() -replace "[^a-z' ]", " " -split "\s+") | Where-Object { $_ -ne "" }
    $hit = ($want | Where-Object { $got -contains $_ }).Count
    $results += [pscustomobject]@{ clip = "$($scene.id)_$i"; expected_words = $want.Count; matched = $hit; ratio = [math]::Round($hit / [math]::Max(1, $want.Count), 2); heard = $text }
  }
}
$results | ConvertTo-Json | Set-Content (Join-Path $here "build\speech_check.json") -Encoding utf8
$results | Format-Table clip, expected_words, matched, ratio -AutoSize | Out-String -Width 200
"overall: " + [math]::Round((($results | Measure-Object matched -Sum).Sum / ($results | Measure-Object expected_words -Sum).Sum), 3)
