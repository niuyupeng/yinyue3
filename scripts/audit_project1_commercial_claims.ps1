param(
    [string]$PackageDir = "",
    [string]$OutJson = "results/project1_commercial_claims_audit_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot\common_project_python.ps1"

$argsList = @("-m", "chorale.commercial_claims_audit", "--out-json", $OutJson)
if ($PackageDir -ne "") {
    $argsList += @("--package-dir", $PackageDir)
}

Write-Host "Auditing Project1 public-facing commercial claims..."
if ($PackageDir -ne "") {
    Write-Host "PackageDir: $PackageDir"
}
Write-Host "OutJson: $OutJson"

Invoke-ProjectPython $argsList
