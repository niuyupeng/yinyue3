param(
    [string]$PackageDir = "",
    [Parameter(Mandatory = $true)]
    [string]$ScoreId,
    [Parameter(Mandatory = $true)]
    [string]$Variant,
    [double]$TimeSec = -1,
    [double]$WindowQuarter = 1.0,
    [string]$OutDir = "results/project1_issue_packets",
    [string]$PacketName = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$argsList = @(
    "-m", "chorale.delivery_issue_packet",
    "--score-id", $ScoreId,
    "--variant", $Variant,
    "--window-quarter", "$WindowQuarter",
    "--out-dir", $OutDir
)
if ($TimeSec -ge 0) {
    $argsList += @("--time-sec", "$TimeSec")
}
if ($PackageDir -ne "") {
    $argsList += @("--package-dir", $PackageDir)
}
if ($PacketName -ne "") {
    $argsList += @("--packet-name", $PacketName)
}

& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Project1 issue evidence packet generation failed."
}
