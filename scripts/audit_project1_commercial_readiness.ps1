param(
    [string]$Root = ".",
    [string]$OutJson = "results/project1_commercial_readiness_audit.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host "Auditing Project1 aggregate commercial readiness..."
Write-Host "Root: $Root"
Write-Host "OutJson: $OutJson"

& $python -m chorale.commercial_readiness_audit --root $Root --out-json $OutJson
if ($LASTEXITCODE -ne 0) {
    throw "Commercial readiness audit failed."
}

Write-Host ""
Write-Host "Readiness audit written to $OutJson"
Write-Host "Markdown summary written to $($OutJson -replace '\.json$', '.md')"
