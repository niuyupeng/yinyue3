param(
    [string]$RatingsDir = "expert_eval/project1/returned_ratings",
    [string]$OutJson = "results/project1_expert_return_intake_report_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python -m chorale.expert_return_intake --ratings-dir $RatingsDir --out-json $OutJson
if ($LASTEXITCODE -ne 0) {
    throw "Project1 expert return intake validation failed."
}
