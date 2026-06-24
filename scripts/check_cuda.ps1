param(
    [switch]$RequireCuda
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

if ($RequireCuda) {
    Invoke-ProjectPython @("-m", "chorale.check_cuda", "--require-cuda")
} else {
    Invoke-ProjectPython @("-m", "chorale.check_cuda")
}
