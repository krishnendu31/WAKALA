# Exports submission\WAKALA_Pitch_Deck.pptx to PDF (and optional PNG previews) using installed Microsoft PowerPoint.
# Usage:  powershell -ExecutionPolicy Bypass -File submission\source\export_pdf.ps1 [-PngDir <folder>]
param([string]$PngDir = "")
$sub = Split-Path -Parent $PSScriptRoot
$src = Join-Path $sub "WAKALA_Pitch_Deck.pptx"
$pdf = Join-Path $sub "WAKALA_Pitch_Deck.pdf"
$app = New-Object -ComObject PowerPoint.Application
$p = $app.Presentations.Open($src, $true, $false, $false)
$p.SaveAs($pdf, 32)   # 32 = ppSaveAsPDF
if ($PngDir -ne "") {
  New-Item -ItemType Directory -Force $PngDir | Out-Null
  $i = 1; foreach ($s in $p.Slides) { $s.Export((Join-Path $PngDir "s$i.png"), "PNG", 1600, 900); $i++ }
}
$p.Close(); $app.Quit()
Write-Output "Wrote $pdf"
