param(
    [string]$Config = "configs\cih_s2s_4060ti_16gb.yaml",
    [string]$Checkpoint = "",
    [string]$Output = "results\cih_s2s_metrics.json",
    [switch]$NoProject1Outputs
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $Root
try {
    $argsList = @("-m", "chorale.evaluate", "--config", $Config, "--output", $Output)
    if ($Checkpoint) {
        $argsList += @("--checkpoint", $Checkpoint)
    }
    if ($NoProject1Outputs) {
        $argsList += "--no-project1-outputs"
    }
    & .\.venv\Scripts\python.exe @argsList
}
finally {
    Pop-Location
}
