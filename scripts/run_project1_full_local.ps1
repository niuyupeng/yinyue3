param(
    [switch]$CpuDebug
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

if ($CpuDebug) {
    Write-Warning "Running Project 1 full pipeline in CPU debug mode. This is not the RTX 4060 Ti full experiment."
    & "$PSScriptRoot\check_cuda.ps1"
} else {
    & "$PSScriptRoot\check_cuda.ps1" -RequireCuda
}
Invoke-ProjectPython @("-m", "pip", "install", "-r", "requirements.txt")
Invoke-ProjectPython @("-m", "pip", "install", "-e", ".", "--no-build-isolation")
if ($CpuDebug) {
    & "$PSScriptRoot\run_project1_all_experiments.ps1" -CpuDebug
} else {
    & "$PSScriptRoot\run_project1_all_experiments.ps1"
}
