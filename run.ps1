# Run.ps1 - setup and run the Library Management System on Windows (PowerShell)
param(
    [switch]$Reinstall
)
$venv = "./venv"
if ($Reinstall -or -not (Test-Path $venv)) {
    python -m venv $venv
}
# Activate the venv for this PowerShell session
. $venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python init_db.py
Write-Host "Starting app..."
python app.py