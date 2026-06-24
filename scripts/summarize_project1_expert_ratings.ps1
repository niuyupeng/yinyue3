param(
    [string]$RatingsXlsx = "",
    [string]$RatingsDir = "expert_eval/project1/returned_ratings",
    [string]$OutDir = "results",
    [string]$ValidationJson = "results/project1_expert_return_intake_report_latest.json",
    [switch]$AllowPreliminary
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$argsList = @("-m", "chorale.expert_eval_tools", "--out-dir", $OutDir)
$summaryRatingsDir = $RatingsDir
if ($RatingsXlsx -ne "") {
    $argsList += @("--ratings-xlsx", $RatingsXlsx)
} else {
    if (-not (Test-Path -LiteralPath $RatingsDir)) {
        New-Item -ItemType Directory -Force -Path $RatingsDir | Out-Null
    }
    Write-Host "Validating returned expert rating workbooks..."
    & $python -m chorale.expert_return_intake --ratings-dir $RatingsDir --out-json $ValidationJson
    if ($LASTEXITCODE -ne 0) {
        throw "Expert rating intake validation failed."
    }
    $validation = Get-Content -Raw -Encoding UTF8 -LiteralPath $ValidationJson | ConvertFrom-Json
    if (($validation.status -ne "ready_to_summarize") -and (-not $AllowPreliminary)) {
        $issues = ($validation.release_gate_issues -join "; ")
        throw "Expert ratings are not ready for formal summarization: $issues. Use -AllowPreliminary only for a clearly marked draft/pending table."
    }
    if ($validation.status -eq "ready_to_summarize") {
        $argsList += @("--ratings-dir", $RatingsDir)
    } else {
        Write-Warning "Expert ratings are not formal-ready. Writing an expert-evaluation-pending table instead of summarizing incomplete/invalid files."
        $summaryRatingsDir = "__project1_no_valid_expert_returns__"
        $argsList += @("--ratings-dir", $summaryRatingsDir)
    }
}

Write-Host "Summarizing Project1 expert ratings..."
if ($RatingsXlsx -ne "") {
    Write-Host "RatingsXlsx: $RatingsXlsx"
} else {
    Write-Host "ValidatedRatingsDir: $RatingsDir"
    Write-Host "SummaryRatingsDir: $summaryRatingsDir"
}
& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Expert rating summarization failed."
}
