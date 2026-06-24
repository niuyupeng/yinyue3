param(
    [Parameter(Mandatory=$true)]
    [string]$InputMusicXml,
    [ValidateSet("soprano_to_satb", "bass_to_satb", "masked_infill", "auto")]
    [string]$Task = "auto",
    [ValidateSet("soprano", "alto", "tenor", "bass")]
    [string]$InputRole = "soprano",
    [string]$KnownVoices = "",
    [double]$GridQuarterLength = 0.25,
    [int]$MaxSeqLen = 256,
    [string]$OutputJson = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot\common_project_python.ps1"

$argsList = @(
    "-m", "chorale.score_preflight",
    "--input", $InputMusicXml,
    "--task", $Task,
    "--input-role", $InputRole,
    "--grid-quarter-length", "$GridQuarterLength",
    "--max-seq-len", "$MaxSeqLen"
)

if ($KnownVoices) {
    $argsList += @("--known-voices", $KnownVoices)
}
if ($OutputJson) {
    $argsList += @("--output-json", $OutputJson)
}

Write-Host "Checking user MusicXML input for Project1 SATB harmonization..."
Write-Host "InputMusicXml: $InputMusicXml"
Write-Host "Task: $Task"

Invoke-ProjectPython $argsList
