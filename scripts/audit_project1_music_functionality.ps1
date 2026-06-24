param(
    [string]$BatchSummary = "generated_scores/batch_user_harmonize_authentic_cadence_smoke_v3/batch_harmonization_summary.json",
    [string]$OutJson = "results/project1_music_functionality_audit_latest.json",
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot\common_project_python.ps1"

Write-Host "Auditing Project1 practical music functionality..."
Write-Host "BatchSummary: $BatchSummary"
Write-Host "OutJson: $OutJson"

$argsList = @(
    "-m",
    "chorale.music_functionality_audit",
    "--root",
    ".",
    "--batch-summary",
    $BatchSummary,
    "--out-json",
    $OutJson
)
if ($Strict) {
    $argsList += "--strict"
}

Invoke-ProjectPython $argsList

Write-Host "Music functionality audit written to $OutJson"
