param(
    [string]$PackageDir = "expert_eval/project1/formal_blind_eval_20260616_083300/SEND_TO_EXPERTS_project1_formal_blind_eval_REPAIRED_SCORE_AUDIO_20260619_195507",
    [string]$OutputDir = "",
    [int]$Limit = 0,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$argsList = @(
    "-m", "chorale.pro_playback_package",
    "--package-dir", $PackageDir
)

if ($OutputDir -ne "") {
    $argsList += @("--output-dir", $OutputDir)
}
if ($Limit -gt 0) {
    $argsList += @("--limit", "$Limit")
}
if ($NoZip) {
    $argsList += "--no-zip"
}

Write-Host "Building Project1 pro playback package..."
Write-Host "PackageDir: $PackageDir"
if ($Limit -gt 0) {
    Write-Host "Debug limit: $Limit score(s)"
}
& $python @argsList
