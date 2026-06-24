param(
    [string]$PackageDir = "",
    [string]$OutJson = "results/project1_delivery_player_static_audit_latest.json"
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

& $python -m chorale.delivery_player_static_audit --package-dir $PackageDir --out-json $OutJson
if ($LASTEXITCODE -ne 0) {
    throw "Project1 delivery player static audit failed."
}
