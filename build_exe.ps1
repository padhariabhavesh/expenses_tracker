Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Padharia Expense Tracker — Build Tool   " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Python check ──────────────────────────────────────────────────────
Write-Host "[1/4] Checking Python..." -ForegroundColor Yellow
try {
    $pyVer = python --version 2>&1
    Write-Host "      Found: $pyVer" -ForegroundColor Green
} catch {
    Write-Error "Python is not installed or not in PATH. Aborting."
    exit 1
}

# ── 2. Install / upgrade dependencies ───────────────────────────────────
Write-Host ""
Write-Host "[2/4] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
python -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed. Aborting."
    exit 1
}
Write-Host "      Dependencies OK." -ForegroundColor Green

# ── 3. PyInstaller build ─────────────────────────────────────────────────
Write-Host ""
Write-Host "[3/4] Building executable with PyInstaller..." -ForegroundColor Yellow
python -m PyInstaller Padharia.spec --clean --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed. Check output above for errors."
    exit 1
}

# ── 4. Post-build: copy runtime files ───────────────────────────────────
Write-Host ""
Write-Host "[4/4] Copying runtime files to dist\..." -ForegroundColor Yellow

# .env  (MongoDB URI + SECRET_KEY — required at runtime)
if (Test-Path ".env") {
    Copy-Item ".env" "dist\.env" -Force
    Write-Host "      Copied .env  (MongoDB URI + SECRET_KEY)" -ForegroundColor Green
} else {
    Write-Warning ".env not found - the exe will not connect to MongoDB!"
}

# data folder (if it exists)
if (Test-Path "data") {
    Copy-Item "data" "dist\data" -Recurse -Force
    Write-Host "      Copied data\ folder" -ForegroundColor Green
}

# ── Done ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  BUILD SUCCESSFUL!                       " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Executable : dist\Padharia.exe" -ForegroundColor Cyan
Write-Host "  To run     : .\dist\Padharia.exe" -ForegroundColor Cyan
Write-Host ""
Write-Host "  NOTE: Keep .env in the same folder as Padharia.exe" -ForegroundColor Yellow
Write-Host "        so the app can connect to MongoDB." -ForegroundColor Yellow
Write-Host ""
