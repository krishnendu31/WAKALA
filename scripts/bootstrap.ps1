# WAKALA bootstrap (Windows PowerShell). Creates the backend venv, installs
# all dependencies, then runs backend tests and the frontend production build.
# Usage (from the repository root):  powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "==> Backend: creating virtual environment" -ForegroundColor Cyan
Push-Location "$root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
Write-Host "==> Backend: running tests" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pytest
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Backend tests failed" }
Pop-Location

Write-Host "==> Frontend: installing dependencies" -ForegroundColor Cyan
Push-Location "$root\frontend"
npm install --no-audit --no-fund
Write-Host "==> Frontend: production build" -ForegroundColor Cyan
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Frontend build failed" }
Pop-Location

Write-Host ""
Write-Host "Bootstrap complete. Start the app in two terminals:" -ForegroundColor Green
Write-Host "  cd backend;  .\.venv\Scripts\python.exe run_dev.py"
Write-Host "  cd frontend; npm run dev"
