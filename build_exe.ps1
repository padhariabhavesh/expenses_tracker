Write-Host "Starting Build Process..." -ForegroundColor Cyan

# Check for Python
try {
    python --version
}
catch {
    Write-Error "Python is not installed or not in PATH."
    exit 1
}

# Install Requirements
Write-Host "Installing/Updating Dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt

# Run PyInstaller
Write-Host "Building Executable..." -ForegroundColor Yellow
python -m PyInstaller Padharia.spec --clean --noconfirm

if ($?) {
    Write-Host "Build Success!" -ForegroundColor Green
    Write-Host "Executable is located in: dist\Padharia.exe" -ForegroundColor Cyan
}
else {
    Write-Error "Build Failed."
}
