param(
    [string]$PackageDir = "",
    [string]$ZipFile = "",
    [string]$OutJson = "results/project1_recipient_usability_audit_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if ($PackageDir -ne "" -and $ZipFile -ne "") {
    throw "Pass either -PackageDir or -ZipFile, not both."
}

if ($PackageDir -eq "" -and $ZipFile -eq "") {
    $manifestPath = "results/project1_delivery_release_manifest_latest.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        throw "No package path was provided and $manifestPath is missing."
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.zip_file) {
        $ZipFile = [string]$manifest.zip_file
    } else {
        throw "Latest release manifest has no zip_file field."
    }
}

Write-Host "Auditing Project1 recipient-facing usability..."
if ($ZipFile -ne "") {
    Write-Host "ZIP: $ZipFile"
    & $python -m chorale.delivery_recipient_usability_audit --zip-file $ZipFile --out-json $OutJson
} else {
    Write-Host "PackageDir: $PackageDir"
    & $python -m chorale.delivery_recipient_usability_audit --package-dir $PackageDir --out-json $OutJson
}
if ($LASTEXITCODE -ne 0) {
    throw "Recipient usability audit failed."
}

Write-Host ""
Write-Host "Recipient usability audit written to $OutJson"
Write-Host "Markdown summary written to $($OutJson -replace '\.json$', '.md')"
