$ErrorActionPreference = "Stop"

$BootstrapArgs = @("-3.11")
try {
    & py -3.11 --version *> $null
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11 not found" }
} catch {
    $BootstrapArgs = @("-3.10")
    & py -3.10 --version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.10 or 3.11 is required for the CUDA environment."
    }
}

if (-not (Test-Path ".venv")) {
    & py @BootstrapArgs -m venv .venv
}

$Python = ".\.venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip wheel
& $Python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
& $Python -m pip install -r requirements.txt
& $Python -m pip install -e . --no-build-isolation
& "$PSScriptRoot\check_cuda.ps1" -RequireCuda

Write-Host "CUDA setup complete for Project 1."
