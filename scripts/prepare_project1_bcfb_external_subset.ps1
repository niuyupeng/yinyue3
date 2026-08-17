param(
    [string]$OutDir = "data/raw/bcfb_selected_musicxml",
    [string]$ArchiveDir = "data/raw/bcfb",
    [string]$SummaryJson = "results/project1_bcfb_external_subset_latest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$recordUrl = "https://zenodo.org/records/5084914"
$apiUrl = "https://zenodo.org/api/records/5084914"
$downloadUrl = "https://zenodo.org/api/records/5084914/files/juyaolongpaul/Bach_chorale_FB-v2.0.zip/content"
$expectedMd5 = "05ef08b3f7fdbbb951abd03152de6338"
$zipPath = Join-Path $ArchiveDir "Bach_chorale_FB-v2.0.zip"

New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SummaryJson) | Out-Null

if (-not (Test-Path -LiteralPath $zipPath)) {
    Write-Host "Downloading BCFB from Zenodo..."
    Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath
}

$actualMd5 = (Get-FileHash -Algorithm MD5 -LiteralPath $zipPath).Hash.ToLowerInvariant()
if ($actualMd5 -ne $expectedMd5) {
    throw "BCFB archive MD5 mismatch. Expected $expectedMd5 but got $actualMd5."
}

Expand-Archive -LiteralPath $zipPath -DestinationPath $ArchiveDir -Force

$musicXmlRoot = Get-ChildItem -Recurse -Directory -LiteralPath $ArchiveDir |
    Where-Object { $_.FullName -like "*FB_source*musicXML_master" } |
    Select-Object -First 1

if ($null -eq $musicXmlRoot) {
    throw "Could not find FB_source/musicXML_master after extracting BCFB."
}

Remove-Item -LiteralPath $OutDir -Recurse -Force
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$selectedFiles = Get-ChildItem -LiteralPath $musicXmlRoot.FullName -File -Filter "*.musicxml" | Sort-Object Name
foreach ($file in $selectedFiles) {
    Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $OutDir $file.Name)
}

$ignoredDirs = Get-ChildItem -LiteralPath $musicXmlRoot.FullName -Directory | Sort-Object Name | Select-Object -ExpandProperty Name
$summary = [ordered]@{
    schema = "project1_bcfb_external_subset_v1"
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("s") + "Z"
    source_name = "Bach Chorales Figured Bass (BCFB) dataset"
    source_record_url = $recordUrl
    source_api_url = $apiUrl
    source_doi = "10.5281/zenodo.5084914"
    source_license = "CC-BY-4.0"
    archive_path = $zipPath
    archive_md5 = $actualMd5
    extracted_musicxml_root = $musicXmlRoot.FullName
    selected_musicxml_dir = (Resolve-Path -LiteralPath $OutDir).Path
    selected_top_level_musicxml_count = $selectedFiles.Count
    ignored_musicxml_master_subdirectories = @($ignoredDirs)
    notes = @(
        "Only top-level FB_source/musicXML_master .musicxml files are selected.",
        "The BCFB source page instructs users to ignore editorial_ones, editorial_FB_only, and BCMCL subfolders.",
        "This subset is a real external MusicXML source check, but it is still Bach chorale material and should not be reported as external-repertory generalization."
    )
}

$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SummaryJson -Encoding UTF8

$summaryMd = [System.IO.Path]::ChangeExtension($SummaryJson, ".md")
@(
    "# Project1 BCFB External MusicXML Subset",
    "",
    "Source: Bach Chorales Figured Bass (BCFB) dataset",
    "",
    "- Record: $recordUrl",
    "- DOI: 10.5281/zenodo.5084914",
    "- License: CC-BY-4.0",
    "- Archive MD5: $actualMd5",
    "- Selected MusicXML directory: $((Resolve-Path -LiteralPath $OutDir).Path)",
    "- Selected top-level MusicXML files: $($selectedFiles.Count)",
    "- Ignored subdirectories under musicXML_master: $($ignoredDirs -join ', ')",
    "",
    "This subset is a real external MusicXML source check, but it remains Bach chorale material and is not external-repertory evidence."
) | Set-Content -LiteralPath $summaryMd -Encoding UTF8

Write-Host "BCFB selected MusicXML files: $($selectedFiles.Count)"
Write-Host "Summary written to $SummaryJson"
