$ErrorActionPreference = "Stop"

$BootstrapPython = "python"
try {
    py -3.11 --version | Out-Null
    $BootstrapPython = "py -3.11"
} catch {
    try {
        py -3.10 --version | Out-Null
        $BootstrapPython = "py -3.10"
    } catch {
        $BootstrapPython = "python"
    }
}

if (-not (Test-Path ".venv")) {
    Invoke-Expression "$BootstrapPython -m venv .venv"
}

$Python = ".\.venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install -e . --no-build-isolation

Write-Host "Setup complete. Python: $Python"
