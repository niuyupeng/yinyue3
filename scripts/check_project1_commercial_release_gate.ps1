param(
    [string]$Root = ".",
    [string]$OutJson = "results/project1_commercial_release_gate_latest.json",
    [int]$MinRaters = 3,
    [int]$MinAbsoluteRows = 1,
    [int]$MinPairedRows = 1,
    [switch]$Strict
)

. "$PSScriptRoot\common_project_python.ps1"

Write-Host "Checking Project1 final commercial release gate..."
Write-Host "Root: $Root"
Write-Host "OutJson: $OutJson"

$argsList = @(
    "-m", "chorale.commercial_release_gate",
    "--root", $Root,
    "--out-json", $OutJson,
    "--min-raters", "$MinRaters",
    "--min-absolute-rows", "$MinAbsoluteRows",
    "--min-paired-rows", "$MinPairedRows"
)

Invoke-ProjectPython $argsList

if ($Strict) {
    $report = Get-Content -Raw -Path $OutJson | ConvertFrom-Json
    if (-not $report.commercial_release_ready) {
        Write-Host ("Project1 commercial release gate BLOCKED: " + ($report.blocking_items -join ", ")) -ForegroundColor Red
        exit 2
    }
}
