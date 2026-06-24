param(
    [string]$Out = "docs/project1_100_point_release_checklist.md"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot\common_project_python.ps1"

Write-Host "Writing Project1 100/100 release checklist from current audit evidence..."
Invoke-ProjectPython @("-m", "chorale.release_checklist", "--root", ".", "--out", $Out)
Write-Host "Release checklist written to $Out"
