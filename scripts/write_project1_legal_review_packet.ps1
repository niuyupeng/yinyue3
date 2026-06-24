param(
    [string]$OutDir = "results/project1_commercial_legal_review_packet",
    [string]$DeliveryZip = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if ($DeliveryZip -eq "") {
    $releaseManifest = "results/project1_delivery_release_manifest_latest.json"
    if (-not (Test-Path -LiteralPath $releaseManifest)) {
        throw "Latest delivery release manifest not found: $releaseManifest"
    }
    $release = Get-Content -LiteralPath $releaseManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $DeliveryZip = [string]$release.zip_file
}

Write-Host "Writing Project1 commercial/legal review packet..."
Write-Host "OutDir: $OutDir"
Write-Host "DeliveryZip: $DeliveryZip"

& $python -m chorale.commercial_legal_packet --out-dir $OutDir --delivery-zip $DeliveryZip
if ($LASTEXITCODE -ne 0) {
    throw "Commercial/legal review packet generation failed."
}
