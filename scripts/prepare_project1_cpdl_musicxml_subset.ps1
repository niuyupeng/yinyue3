param(
    [string]$OutDir = "data/raw/cpdl_selected_musicxml",
    [string]$SummaryJson = "results/project1_cpdl_musicxml_subset_latest.json",
    [int]$MaxCategoryPages = 3,
    [int]$MaxWorkPages = 200,
    [int]$MaxFiles = 40,
    [int]$MaxFilesPerWork = 1,
    [double]$RequestDelaySeconds = 0.5,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. .\scripts\common_project_python.ps1

$pythonArgs = @(
    "-m",
    "chorale.cpdl_musicxml_subset",
    "--out-dir",
    $OutDir,
    "--summary-json",
    $SummaryJson,
    "--max-category-pages",
    "$MaxCategoryPages",
    "--max-work-pages",
    "$MaxWorkPages",
    "--max-files",
    "$MaxFiles",
    "--max-files-per-work",
    "$MaxFilesPerWork",
    "--request-delay-seconds",
    "$RequestDelaySeconds"
)

if ($Clean) {
    $pythonArgs += "--clean"
}

Write-Host "Preparing CPDL SATB MusicXML candidate subset for Project1..."
Write-Host "OutDir: $OutDir"
Write-Host "SummaryJson: $SummaryJson"
Write-Host "MaxFiles: $MaxFiles"
Invoke-ProjectPython -PythonArgs $pythonArgs

Write-Host ""
Write-Host "CPDL candidate subset summary written to $SummaryJson"
Write-Host "Markdown summary written to $($SummaryJson -replace '\.json$', '.md')"
