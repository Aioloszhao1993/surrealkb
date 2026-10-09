# SurrealVideo one-click start: MySQL + FastAPI backend + Vite frontend
# Usage: right-click "Run with PowerShell", or in a terminal: .\start-all.ps1

$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }

Write-Host "=======================================" -ForegroundColor Magenta
Write-Host "  SurrealVideo  start" -ForegroundColor Magenta
Write-Host "=======================================" -ForegroundColor Magenta

# ---------- 1) MySQL ----------
Write-Host "`n[1/3] MySQL ..." -ForegroundColor Cyan
& "$root\start-mysql.ps1"

# ---------- 2) Backend (FastAPI) ----------
Write-Host "`n[2/3] FastAPI backend ..." -ForegroundColor Cyan
$venvPy = "$root\backend\.venv\Scripts\python.exe"

function Test-PyUsable([string]$exe) {
    if (-not (Test-Path $exe)) { return $false }
    & $exe -c "import sys" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Find-Py311 {
    $cands = @()
    if ($env:QCLAW_PYTHON_BINARY) { $cands += $env:QCLAW_PYTHON_BINARY }
    $cands += @(Get-ChildItem "D:\QClaw\*\resources\python\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    $g = Get-Command python -ErrorAction SilentlyContinue
    if ($g) { $cands += $g.Source }
    foreach ($c in $cands) {
        if ($c -and (Test-Path $c)) {
            $v = & $c -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
            if ("$v".Trim() -eq "3.11") { return $c }
        }
    }
    return $null
}

if (-not (Test-PyUsable $venvPy)) {
    Write-Host "Backend venv is broken or missing - repairing ..." -ForegroundColor Yellow
    $base = Find-Py311
    if ($base -and (Test-Path "$root\backend\.venv")) {
        # cheap fix: repoint pyvenv.cfg at a live base interpreter
        $cfg = "home = " + (Split-Path $base) + "`r`ninclude-system-site-packages = false`r`nversion = 3.11.10`r`nexecutable = $base`r`n"
        Set-Content -Path "$root\backend\.venv\pyvenv.cfg" -Value $cfg -Encoding ASCII
    }
    if (-not (Test-PyUsable $venvPy)) {
        # full rebuild
        if (-not $base) { $base = "python" }
        if (Test-Path "$root\backend\.venv") { Remove-Item -Recurse -Force "$root\backend\.venv" }
        & $base -m venv "$root\backend\.venv"
    }
    & $venvPy -m pip install -q -r "$root\backend\requirements.txt"
    Write-Host "Backend venv ready." -ForegroundColor Green
}

if (-not (Test-Path "$root\backend\.env")) {
    Copy-Item "$root\backend\.env.example" "$root\backend\.env"
    Write-Host "Generated backend\.env" -ForegroundColor Yellow
}
Start-Process -FilePath powershell -ArgumentList "-NoExit","-Command","Set-Location '$root\backend'; & '$venvPy' -m uvicorn app.main:app --reload --port 8000"

# ---------- 3) Frontend (Vite) ----------
Write-Host "`n[3/3] Vite frontend ..." -ForegroundColor Cyan
Push-Location "$root\frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "npm install ..." -ForegroundColor Yellow
    npm install
}
Pop-Location
Start-Process -FilePath powershell -ArgumentList "-NoExit","-Command","Set-Location '$root\frontend'; npm run dev"

Start-Sleep -Seconds 8
Write-Host "`n=======================================" -ForegroundColor Green
Write-Host "  Started" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  Frontend : http://localhost:5173" -ForegroundColor Green
Write-Host "  API docs : http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "`n  Stop MySQL     : .\stop-mysql.ps1" -ForegroundColor Yellow
Write-Host "  Stop web apps  : close the two popup windows, or run .\stop-all.ps1" -ForegroundColor Yellow
