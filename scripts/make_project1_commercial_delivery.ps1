param(
    [string]$MasterPackage = "expert_eval/project1/pro_playback_rawxml_full_20260619_222205",
    [string]$OutputRoot = "expert_eval/project1/deliverables",
    [switch]$SkipZip
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if (-not (Test-Path -LiteralPath $MasterPackage)) {
    throw "Master playback package not found: $MasterPackage"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$stage = Join-Path $OutputRoot "project1_pro_playback_mp3_100_FINAL_$stamp"
New-Item -ItemType Directory -Path $stage | Out-Null

$requiredDirs = @(
    "absolute_score_musicxml",
    "absolute_score_pdfs",
    "paired_comparison_musicxml",
    "paired_comparison_pdfs",
    "forms",
    "render_xml",
    "midi_pro"
)
foreach ($dir in $requiredDirs) {
    $src = Join-Path $MasterPackage $dir
    if (-not (Test-Path -LiteralPath $src)) {
        throw "Required delivery source folder missing: $src"
    }
    Copy-Item -LiteralPath $src -Destination (Join-Path $stage $dir) -Recurse
}

$topFiles = @(
    "COMMERCIAL_PLAYBACK_README_CN.md",
    "README_CN.md",
    "README_FOR_EXPERTS.md",
    "EMAIL_TEMPLATE_TO_EXPERTS.md",
    "SCORING_RUBRIC.md",
    "RETURN_FILES_CHECKLIST.md",
    "SCORE_AUDIO_CORRESPONDENCE.csv",
    "SCORE_AUDIO_CORRESPONDENCE_README.md",
    "SCORE_AUDIO_CORRESPONDENCE_SUMMARY.json"
)
foreach ($file in $topFiles) {
    $src = Join-Path $MasterPackage $file
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $stage $file)
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $stage "audio_pro") | Out-Null
$audioFiles = @(
    "pro_playback_summary.json",
    "commercial_qc_report.csv",
    "commercial_qc_summary.json",
    "COMMERCIAL_QC_REPORT.md",
    "README_PRO_PLAYBACK.md"
)
foreach ($file in $audioFiles) {
    $src = Join-Path $MasterPackage "audio_pro/$file"
    if (-not (Test-Path -LiteralPath $src)) {
        throw "Required delivery source file missing: $src"
    }
    Copy-Item -LiteralPath $src -Destination (Join-Path $stage "audio_pro/$file")
}

$masterAudio = Join-Path (Resolve-Path $MasterPackage).Path "audio_pro"
Get-ChildItem -LiteralPath $masterAudio -Recurse -Filter "*.mp3" | ForEach-Object {
    $rel = $_.FullName.Substring($masterAudio.Length).TrimStart("\")
    $dest = Join-Path (Join-Path $stage "audio_pro") $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $dest
}

& $python -m chorale.score_audio_correspondence `
    --package-dir $stage `
    --source-manifest (Join-Path $MasterPackage "audio_pro/pro_playback_manifest.csv") `
    --stage-manifest (Join-Path $stage "audio_pro/pro_playback_manifest.csv")
if ($LASTEXITCODE -ne 0) {
    throw "Score-audio correspondence generation failed."
}

@"
# MP3-only delivery note

This folder is the lightweight expert/customer delivery subset derived from the full QC-passed master package.

- Included: MP3 playback, source MusicXML, render MusicXML, MIDI, PDFs, forms, local HTML player, QC summaries.
- Not included: WAV masters, to keep the share package compact.
- Full master folder on the workstation: $MasterPackage
- The commercial QC score of 100/100 was computed on the full master package before this MP3-only subset was created.
"@ | Set-Content -LiteralPath (Join-Path $stage "MP3_ONLY_DELIVERY_NOTE.md") -Encoding UTF8

& $python -m chorale.delivery_package_docs --package-dir $stage --master-package $MasterPackage
if ($LASTEXITCODE -ne 0) {
    throw "Delivery README generation failed."
}

& $python -m chorale.playback_license_audit --package-dir $stage --write-notices --out-json (Join-Path $stage "PLAYBACK_LICENSE_AUDIT.json")
if ($LASTEXITCODE -ne 0) {
    throw "Playback license audit failed."
}

& $python -m chorale.expert_eval_tools --package-dir $stage --write-xlsx
if ($LASTEXITCODE -ne 0) {
    throw "Expert XLSX form generation failed."
}

& $python -m chorale.pro_playback_index --package-dir $stage
if ($LASTEXITCODE -ne 0) {
    throw "Playback index strict validation failed."
}

& $python -m chorale.delivery_recipient_tools --package-dir $stage
if ($LASTEXITCODE -ne 0) {
    throw "Recipient-side integrity verifier generation failed."
}

$preManifest = & $python -m chorale.delivery_integrity --package-dir $stage --write
if ($LASTEXITCODE -ne 0) {
    throw "Initial delivery integrity manifest generation failed."
}

$auditJson = Join-Path $stage "COMMERCIAL_DELIVERY_AUDIT.json"

$playerAuditJson = Join-Path $stage "DELIVERY_PLAYER_STATIC_AUDIT.json"
& $python -m chorale.delivery_player_static_audit --package-dir $stage --out-json $playerAuditJson
if ($LASTEXITCODE -ne 0) {
    throw "Delivery player static audit failed."
}
New-Item -ItemType Directory -Force -Path "results" | Out-Null
Copy-Item -LiteralPath $playerAuditJson -Destination "results/project1_delivery_player_static_audit_latest.json" -Force
Copy-Item -LiteralPath ([System.IO.Path]::ChangeExtension($playerAuditJson, ".md")) -Destination "results/project1_delivery_player_static_audit_latest.md" -Force

$mediaAuditJson = Join-Path $stage "DELIVERY_MEDIA_AUDIT.json"
& $python -m chorale.delivery_media_audit --package-dir $stage --out-json $mediaAuditJson
if ($LASTEXITCODE -ne 0) {
    throw "Delivery media content audit failed."
}
Copy-Item -LiteralPath $mediaAuditJson -Destination "results/project1_delivery_media_audit_latest.json" -Force
Copy-Item -LiteralPath ([System.IO.Path]::ChangeExtension($mediaAuditJson, ".csv")) -Destination "results/project1_delivery_media_audit_latest.csv" -Force
Copy-Item -LiteralPath ([System.IO.Path]::ChangeExtension($mediaAuditJson, ".md")) -Destination "results/project1_delivery_media_audit_latest.md" -Force

$conformanceAuditJson = Join-Path $stage "DELIVERY_CONFORMANCE_AUDIT.json"
& $python -m chorale.delivery_conformance_audit --package-dir $stage --out-json $conformanceAuditJson
if ($LASTEXITCODE -ne 0) {
    throw "Delivery score-playback conformance audit failed."
}
Copy-Item -LiteralPath $conformanceAuditJson -Destination "results/project1_delivery_conformance_audit_latest.json" -Force
Copy-Item -LiteralPath ([System.IO.Path]::ChangeExtension($conformanceAuditJson, ".csv")) -Destination "results/project1_delivery_conformance_audit_latest.csv" -Force
Copy-Item -LiteralPath ([System.IO.Path]::ChangeExtension($conformanceAuditJson, ".md")) -Destination "results/project1_delivery_conformance_audit_latest.md" -Force

$recipientUsabilityJson = Join-Path $stage "RECIPIENT_USABILITY_AUDIT.json"
& $python -m chorale.delivery_recipient_usability_audit --package-dir $stage --out-json $recipientUsabilityJson
if ($LASTEXITCODE -ne 0) {
    throw "Recipient-facing usability audit failed."
}
Copy-Item -LiteralPath $recipientUsabilityJson -Destination "results/project1_recipient_usability_audit_latest.json" -Force
Copy-Item -LiteralPath ([System.IO.Path]::ChangeExtension($recipientUsabilityJson, ".md")) -Destination "results/project1_recipient_usability_audit_latest.md" -Force

& $python -m chorale.delivery_integrity --package-dir $stage --write --verify --out-json (Join-Path $stage "DELIVERY_INTEGRITY_REPORT.json")
if ($LASTEXITCODE -ne 0) {
    throw "Final delivery integrity manifest generation or verification failed."
}

& $python -m chorale.commercial_delivery_audit --package-dir $stage --mode mp3_only --out-json $auditJson
if ($LASTEXITCODE -ne 0) {
    throw "Final commercial delivery folder audit failed."
}
Copy-Item -LiteralPath $auditJson -Destination "results/project1_commercial_delivery_audit_latest.json" -Force
Copy-Item -LiteralPath ([System.IO.Path]::ChangeExtension($auditJson, ".md")) -Destination "results/project1_commercial_delivery_audit_latest.md" -Force

& $python -m chorale.delivery_integrity --package-dir $stage --write --verify --out-json (Join-Path $stage "DELIVERY_INTEGRITY_REPORT.json")
if ($LASTEXITCODE -ne 0) {
    throw "Post-audit delivery integrity manifest generation or verification failed."
}
Copy-Item -LiteralPath (Join-Path $stage "DELIVERY_INTEGRITY_REPORT.json") -Destination "results/project1_delivery_integrity_report_latest.json" -Force
Copy-Item -LiteralPath (Join-Path $stage "DELIVERY_INTEGRITY_REPORT.md") -Destination "results/project1_delivery_integrity_report_latest.md" -Force

$zip = ""
if (-not $SkipZip) {
    $zip = Join-Path $OutputRoot ("project1_pro_playback_mp3_100_FINAL_$stamp.zip")
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
}

if ($zip -ne "") {
    & $python -m chorale.commercial_delivery_audit --zip-file $zip --mode mp3_only --out-json (Join-Path $OutputRoot "latest_commercial_delivery_zip_audit.json")
    if ($LASTEXITCODE -ne 0) {
        throw "Commercial delivery ZIP audit failed."
    }
    & $python -m chorale.delivery_integrity --zip-file $zip --verify --out-json "results/project1_delivery_zip_integrity_report_latest.json"
    if ($LASTEXITCODE -ne 0) {
        throw "Commercial delivery ZIP integrity verification failed."
    }
    & $python -m chorale.delivery_release_manifest --zip-file $zip --out-json "results/project1_delivery_release_manifest_latest.json"
    if ($LASTEXITCODE -ne 0) {
        throw "Delivery release manifest generation failed."
    }
    $releaseJson = [System.IO.Path]::ChangeExtension($zip, ".release.json")
    & $python -m chorale.delivery_release_manifest --zip-file $zip --out-json $releaseJson
    if ($LASTEXITCODE -ne 0) {
        throw "Adjacent delivery release manifest generation failed."
    }
    & $python -m chorale.delivery_release_manifest --verify-manifest "results/project1_delivery_release_manifest_latest.json"
    if ($LASTEXITCODE -ne 0) {
        throw "Delivery release manifest verification failed."
    }
}

& $python -m chorale.delivery_integrity --package-dir $stage --verify --out-json "results/project1_delivery_integrity_report_latest.json"
if ($LASTEXITCODE -ne 0) {
    throw "Latest delivery integrity verification failed."
}

$mp3Count = (Get-ChildItem -LiteralPath (Join-Path $stage "audio_pro") -Recurse -Filter "*.mp3").Count
$midiCount = (Get-ChildItem -LiteralPath $stage -Recurse -Filter "*.mid").Count
$wavCount = (Get-ChildItem -LiteralPath $stage -Recurse -Filter "*.wav").Count

[PSCustomObject]@{
    stage = (Resolve-Path $stage).Path
    zip = $zip
    mp3_count = $mp3Count
    midi_count = $midiCount
    wav_count = $wavCount
} | ConvertTo-Json -Depth 3
