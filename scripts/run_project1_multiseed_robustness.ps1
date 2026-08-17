param(
    [string]$Config = "configs/chorale_rule_guided_decoding.yaml",
    [string[]]$Seeds = @("2027", "2028"),
    [string]$RunRoot = "runs/project1_multiseed",
    [string]$OutCsv = "results/project1_multiseed_summary.csv",
    [string]$OutJson = "results/project1_robustness_summary.json",
    [switch]$IncludeExistingPrimary,
    [switch]$FastDevRun,
    [switch]$ForceRerun,
    [int]$MaxEvalBatches = 0
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

& "$PSScriptRoot\check_cuda.ps1" -RequireCuda

$argsList = @(
    "-m", "chorale.robustness",
    "--config", $Config,
    "--seeds"
)
$argsList += $Seeds
$argsList += @(
    "--run-root", $RunRoot,
    "--out-csv", $OutCsv,
    "--out-json", $OutJson
)

if ($IncludeExistingPrimary) {
    $argsList += "--include-existing-primary"
}
if ($FastDevRun) {
    $argsList += "--fast-dev-run"
}
if ($ForceRerun) {
    $argsList += "--force-rerun"
}
if ($MaxEvalBatches -gt 0) {
    $argsList += @("--max-eval-batches", "$MaxEvalBatches")
}

Invoke-ProjectPython $argsList

Write-Host ""
Write-Host "Project1 multi-seed robustness summary written to $OutJson"
Write-Host "Project1 multi-seed rows written to $OutCsv"
