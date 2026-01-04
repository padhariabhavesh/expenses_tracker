Write-Host "Repairing Virtual Environment..."
if (Test-Path "venv") {
    Write-Host "Removing broken venv..."
    Remove-Item -Path "venv" -Recurse -Force
}

Write-Host "Creating new venv..."
python -m venv venv

Write-Host "Installing dependencies..."
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Environment Repaired. You can now build the app."
