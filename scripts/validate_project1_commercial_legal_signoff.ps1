param(
    [string]$SignoffPath = "results/project1_commercial_legal_signoff.json",
    [string]$OutJson = "results/project1_commercial_legal_signoff_validation_latest.json",
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot\common_project_python.ps1"

Write-Host "Validating Project1 commercial/legal signoff..."
Write-Host "SignoffPath: $SignoffPath"
Write-Host "OutJson: $OutJson"

Invoke-ProjectPython @(
    "-m", "chorale.commercial_legal_signoff",
    "--validate",
    "--signoff-path", $SignoffPath,
    "--validation-out", $OutJson
)

if ($Strict) {
    $report = Get-Content -LiteralPath $OutJson -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $report.ready_for_commercial_release_gate) {
        Write-Host ("Project1 commercial/legal signoff BLOCKED: " + ($report.problems -join "; ")) -ForegroundColor Red
        exit 2
    }
}
