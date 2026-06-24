param(
    [string]$ZipFile = "",
    [string]$OutJson = "results/project1_delivery_release_manifest_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if ($ZipFile -eq "") {
    $latest = Get-ChildItem -File "expert_eval\project1\deliverables\*.zip" |
        Where-Object { $_.Name -like "project1_pro_playback_mp3_100_FINAL_*.zip" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $latest) {
        throw "No project1_pro_playback_mp3_100_FINAL_*.zip found."
    }
    $ZipFile = $latest.FullName
}

$root = (Get-Location).Path
$resolvedZip = (Resolve-Path -LiteralPath $ZipFile).Path
if ($resolvedZip.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
    $ZipFile = $resolvedZip.Substring($root.Length).TrimStart('\', '/')
} else {
    $ZipFile = $resolvedZip
}

Write-Host "Writing Project1 delivery release manifest..."
Write-Host "ZipFile: $ZipFile"
Write-Host "OutJson: $OutJson"

& $python -m chorale.delivery_release_manifest --zip-file $ZipFile --out-json $OutJson
if ($LASTEXITCODE -ne 0) {
    throw "Release manifest generation failed."
}

& $python -m chorale.delivery_release_manifest --verify-manifest $OutJson
if ($LASTEXITCODE -ne 0) {
    throw "Release manifest verification failed."
}
