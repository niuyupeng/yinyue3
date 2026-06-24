param(
    [string]$PackageDir = "",
    [ValidateSet("master", "mp3_only")]
    [string]$Mode = "master",
    [string]$OutJson = "results/project1_pro_playback_traceability_audit_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if ($PackageDir -eq "") {
    $latest = Get-ChildItem -Directory "expert_eval\project1" |
        Where-Object { $_.Name -like "pro_playback_rawxml_full_*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $latest) {
        throw "No pro_playback_rawxml_full_* package found under expert_eval\project1."
    }
    $PackageDir = $latest.FullName
}

Write-Host "Auditing pro playback score-audio traceability..."
Write-Host "PackageDir: $PackageDir"
Write-Host "Mode: $Mode"
Write-Host "OutJson: $OutJson"

& $python -m chorale.pro_playback_traceability_audit --package-dir $PackageDir --mode $Mode --out-json $OutJson
if ($LASTEXITCODE -ne 0) {
    throw "Pro playback traceability audit failed."
}
