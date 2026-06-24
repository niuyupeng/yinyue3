param(
    [string]$PackageDir = "",
    [Parameter(Mandatory = $true)]
    [string]$ScoreId,
    [Parameter(Mandatory = $true)]
    [string]$Variant,
    [double]$TimeSec = -1,
    [double]$WindowQuarter = 1.0,
    [string]$OutJson = "results/project1_delivery_item_debug_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$argsList = @(
    "-m", "chorale.delivery_issue_debugger",
    "--score-id", $ScoreId,
    "--variant", $Variant,
    "--out-json", $OutJson
)
if ($TimeSec -ge 0) {
    $argsList += @("--time-sec", "$TimeSec", "--window-quarter", "$WindowQuarter")
}
if ($PackageDir -ne "") {
    $argsList += @("--package-dir", $PackageDir)
}

& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Project1 delivery item debug reported an issue."
}
