param(
    [string]$PackageDir = "",
    [string]$ZipFile = "",
    [string]$ManifestJson = "",
    [string]$OutJson = "results/project1_delivery_integrity_report_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if ($PackageDir -ne "" -and $ZipFile -ne "") {
    throw "Provide only one of -PackageDir or -ZipFile."
}

if ($PackageDir -eq "" -and $ZipFile -eq "") {
    $latest = Get-ChildItem -Directory "expert_eval\project1\deliverables" |
        Where-Object { $_.Name -like "project1_pro_playback_mp3_100_FINAL_*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $latest) {
        throw "No project1_pro_playback_mp3_100_FINAL_* folder found under expert_eval\project1\deliverables."
    }
    $PackageDir = $latest.FullName
}

$argsList = @("-m", "chorale.delivery_integrity", "--verify", "--out-json", $OutJson)
if ($ZipFile -ne "") {
    $argsList += @("--zip-file", $ZipFile)
} else {
    $argsList += @("--package-dir", $PackageDir)
}
if ($ManifestJson -ne "") {
    $argsList += @("--manifest-json", $ManifestJson)
}

Write-Host "Verifying Project1 delivery integrity..."
if ($ZipFile -ne "") {
    Write-Host "ZipFile: $ZipFile"
} else {
    Write-Host "PackageDir: $PackageDir"
}
Write-Host "OutJson: $OutJson"
& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Delivery integrity verification failed."
}
