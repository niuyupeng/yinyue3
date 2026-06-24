param(
    [string]$IssuesPath = "expert_eval/project1/returned_issues",
    [string]$PackageDir = "",
    [string]$OutJson = "results/project1_review_issue_intake_latest.json",
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$argsList = @(
    "-m", "chorale.review_issue_intake",
    "--issues-path", $IssuesPath,
    "--out-json", $OutJson
)
if ($PackageDir -ne "") {
    $argsList += @("--package-dir", $PackageDir)
}
if ($Strict) {
    $argsList += "--strict"
}

Write-Host "Ingesting Project1 returned review issue reports..."
Write-Host "IssuesPath: $IssuesPath"
Write-Host "OutJson: $OutJson"

& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Project1 review issue intake failed."
}
