param(
    [string]$OutJson = "results/project1_commercial_release_candidate_latest.json",
    [string]$ChromePath = "",
    [switch]$RunChromeQa,
    [switch]$UseExistingChromeQa,
    [switch]$SkipMediaAudits,
    [switch]$StrictEngineering,
    [switch]$StrictCustomerReview,
    [switch]$StrictCommercial
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot\common_project_python.ps1"

Write-Host "Running Project1 release-candidate audit..."

$latest = Get-ChildItem -File "expert_eval\project1\deliverables\*.zip" |
    Where-Object { $_.Name -like "project1_pro_playback_mp3_100_FINAL_*.zip" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($null -eq $latest) {
    throw "No project1_pro_playback_mp3_100_FINAL_*.zip found."
}

$zipFile = $latest.FullName
$root = (Get-Location).Path
if ($zipFile.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
    $zipFile = $zipFile.Substring($root.Length).TrimStart('\', '/')
}
$packageDir = Join-Path ([System.IO.Path]::GetDirectoryName($zipFile)) ([System.IO.Path]::GetFileNameWithoutExtension($zipFile))

Write-Host "Release ZIP: $zipFile"
Write-Host "Release package dir: $packageDir"

$chromeQaAlreadyRun = $false
if ($RunChromeQa -and $UseExistingChromeQa) {
    throw "Choose either -RunChromeQa or -UseExistingChromeQa, not both."
}
if ($UseExistingChromeQa) {
    $existingChromeQa = "results/project1_delivery_player_qa_latest.json"
    if (-not (Test-Path -LiteralPath $existingChromeQa)) {
        throw "Existing Chrome/Edge QA report not found: $existingChromeQa"
    }
    $qaReport = Get-Content -LiteralPath $existingChromeQa -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($StrictCustomerReview -and [string]$qaReport.status -ne "pass") {
        throw "Existing Chrome/Edge QA report is not a real browser pass: status=$($qaReport.status)"
    }
    if ([string]$qaReport.package_dir -ne $packageDir) {
        throw "Existing Chrome/Edge QA package mismatch: report=$($qaReport.package_dir), current=$packageDir"
    }
    Write-Host "Using existing real browser QA report: $existingChromeQa"
    $chromeQaAlreadyRun = $true
} elseif ($RunChromeQa) {
    $chromeQaArgs = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "$PSScriptRoot\qa_project1_delivery_player_chrome.ps1",
        "-PackageDir",
        $packageDir,
        "-OutJson",
        "results/project1_delivery_player_qa_latest.json"
    )
    if ($ChromePath -ne "") {
        $chromeQaArgs += @("-ChromePath", $ChromePath)
    }
    if ($StrictCustomerReview) {
        $chromeQaArgs += "-StrictBrowser"
    }
    & powershell @chromeQaArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Project1 delivery player Chrome QA failed in isolated PowerShell process."
    }
    $chromeQaAlreadyRun = $true
}

$playbackEnv = "external_tools\playback_env.ps1"
if (Test-Path -LiteralPath $playbackEnv) {
    . $playbackEnv
}

& "$PSScriptRoot\verify_project1_delivery_integrity.ps1" -PackageDir $packageDir -OutJson "results/project1_delivery_integrity_report_latest.json"
& "$PSScriptRoot\verify_project1_delivery_integrity.ps1" -ZipFile $zipFile -OutJson "results/project1_delivery_zip_integrity_report_latest.json"
& "$PSScriptRoot\audit_project1_commercial_delivery.ps1" -ZipFile $zipFile -Mode mp3_only -OutJson "results/project1_commercial_delivery_audit_latest.json"
& "$PSScriptRoot\write_project1_delivery_release_manifest.ps1" -ZipFile $zipFile -OutJson "results/project1_delivery_release_manifest_latest.json"

if (-not $SkipMediaAudits) {
    & "$PSScriptRoot\audit_project1_delivery_media.ps1" -PackageDir $packageDir -OutJson "results/project1_delivery_media_audit_latest.json"
    & "$PSScriptRoot\audit_project1_delivery_conformance.ps1" -PackageDir $packageDir -OutJson "results/project1_delivery_conformance_audit_latest.json"
}

& "$PSScriptRoot\audit_project1_delivery_player_static.ps1" -PackageDir $packageDir -OutJson "results/project1_delivery_player_static_audit_latest.json"
& "$PSScriptRoot\audit_project1_commercial_claims.ps1" -PackageDir $packageDir -OutJson "results/project1_commercial_claims_audit_latest.json"
& "$PSScriptRoot\audit_project1_recipient_usability.ps1" -ZipFile $zipFile -OutJson "results/project1_recipient_usability_audit_latest.json"

if ($RunChromeQa -or $UseExistingChromeQa) {
    if (-not $chromeQaAlreadyRun) {
        throw "Internal error: Chrome QA was requested but did not run before file audits."
    }
} else {
    & "$PSScriptRoot\qa_project1_delivery_player_chrome.ps1" -PackageDir $packageDir -OutJson "results/project1_delivery_player_qa_latest.json" -StaticOnly
}

& "$PSScriptRoot\intake_project1_review_issues.ps1" -PackageDir $packageDir -OutJson "results/project1_review_issue_intake_latest.json"
& "$PSScriptRoot\write_project1_legal_review_packet.ps1" -DeliveryZip $zipFile -OutDir "results/project1_commercial_legal_review_packet"
& "$PSScriptRoot\audit_project1_commercial_readiness.ps1" -OutJson "results/project1_commercial_readiness_audit.json"
& "$PSScriptRoot\write_project1_commercial_acceptance_report.ps1" -OutJson "results/project1_commercial_acceptance_report_latest.json"
& "$PSScriptRoot\write_project1_legal_review_packet.ps1" -DeliveryZip $zipFile -OutDir "results/project1_commercial_legal_review_packet"
& "$PSScriptRoot\write_project1_commercial_acceptance_report.ps1" -OutJson "results/project1_commercial_acceptance_report_latest.json"
& "$PSScriptRoot\check_project1_commercial_release_gate.ps1" -OutJson "results/project1_commercial_release_gate_latest.json"

Invoke-ProjectPython @("-m", "chorale.commercial_release_candidate", "--out-json", $OutJson)
& "$PSScriptRoot\write_project1_release_checklist.ps1" -Out "docs/project1_100_point_release_checklist.md"

$report = Get-Content -LiteralPath $OutJson -Raw -Encoding UTF8 | ConvertFrom-Json

if ($StrictEngineering -and -not $report.engineering_release_candidate_ready) {
    Write-Host ("Project1 engineering release-candidate audit BLOCKED: " + ($report.engineering_blockers -join ", ")) -ForegroundColor Red
    exit 2
}

if ($StrictCustomerReview -and -not $report.customer_review_ready) {
    Write-Host ("Project1 customer-review readiness BLOCKED: " + ($report.customer_review_blockers -join ", ")) -ForegroundColor Red
    exit 4
}

if ($StrictCommercial -and -not $report.commercial_release_ready) {
    Write-Host ("Project1 commercial release audit BLOCKED: " + ($report.commercial_blockers -join ", ")) -ForegroundColor Red
    exit 3
}

Write-Host "Release-candidate audit written to $OutJson"
Write-Host "Engineering release candidate ready: $($report.engineering_release_candidate_ready)"
Write-Host "Customer review ready: $($report.customer_review_ready)"
Write-Host "Commercial release ready: $($report.commercial_release_ready)"
