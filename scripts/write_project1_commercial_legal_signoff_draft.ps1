param(
    [string]$OutJson = "results/project1_commercial_legal_signoff_DRAFT.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot\common_project_python.ps1"

Write-Host "Writing Project1 prefilled commercial/legal signoff draft..."
Write-Host "OutJson: $OutJson"

Invoke-ProjectPython @(
    "-m", "chorale.commercial_legal_signoff",
    "--write-draft",
    "--draft-out", $OutJson
)
