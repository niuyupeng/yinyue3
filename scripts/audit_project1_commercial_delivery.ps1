param(
    [string]$PackageDir = "",
    [string]$ZipFile = "",
    [ValidateSet("mp3_only", "master")]
    [string]$Mode = "mp3_only",
    [string]$OutJson = "results/project1_commercial_delivery_audit_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if ($PackageDir -eq "" -and $ZipFile -eq "") {
    $releaseManifest = "results/project1_delivery_release_manifest_latest.json"
    if (-not (Test-Path -LiteralPath $releaseManifest)) {
        throw "Latest delivery release manifest not found: $releaseManifest"
    }
    $release = Get-Content -LiteralPath $releaseManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $ZipFile = [string]$release.zip_file
}

$argsList = @("-m", "chorale.commercial_delivery_audit", "--mode", $Mode)
if ($PackageDir -ne "") {
    $argsList += @("--package-dir", $PackageDir)
} else {
    $argsList += @("--zip-file", $ZipFile)
}
if ($OutJson -ne "") {
    $argsList += @("--out-json", $OutJson)
}

Write-Host "Auditing Project1 commercial delivery..."
if ($PackageDir -ne "") {
    Write-Host "PackageDir: $PackageDir"
} else {
    Write-Host "ZipFile: $ZipFile"
}
Write-Host "Mode: $Mode"
& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Commercial delivery audit failed."
}
