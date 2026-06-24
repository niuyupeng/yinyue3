param(
    [string]$OutJson = "results/project1_commercial_acceptance_report_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host "Writing Project1 commercial acceptance report..."
Write-Host "OutJson: $OutJson"

& $python -m chorale.commercial_acceptance_report --out-json $OutJson
if ($LASTEXITCODE -ne 0) {
    throw "Commercial acceptance report generation failed."
}
