param(
    [string]$PackageDir = "",
    [string]$ChromePath = "",
    [string]$OutJson = "results/project1_delivery_player_qa_latest.json",
    [string]$Screenshot = "results/project1_delivery_player_qa_latest.png",
    [switch]$StaticOnly,
    [switch]$StrictBrowser
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if ($PackageDir -eq "") {
    $releaseManifest = "results/project1_delivery_release_manifest_latest.json"
    if (-not (Test-Path -LiteralPath $releaseManifest)) {
        throw "Latest delivery release manifest not found: $releaseManifest"
    }
    $release = Get-Content -LiteralPath $releaseManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $zipFile = [string]$release.zip_file
    $PackageDir = Join-Path ([System.IO.Path]::GetDirectoryName($zipFile)) ([System.IO.Path]::GetFileNameWithoutExtension($zipFile))
}

$argsList = @("-m", "chorale.delivery_player_chrome_qa", "--package-dir", $PackageDir, "--out-json", $OutJson, "--screenshot", $Screenshot)
if ($ChromePath -ne "") {
    $argsList += @("--chrome-path", $ChromePath)
}
if ($StaticOnly) {
    $argsList += @("--static-only")
}
if ($StrictBrowser) {
    $argsList += @("--strict-browser")
}

& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Project1 delivery player Chrome QA failed."
}
