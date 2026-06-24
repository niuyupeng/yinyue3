param(
    [Parameter(Mandatory=$true)]
    [string]$InputMusicXml,
    [string]$OutputDir = "generated_scores/user_harmonizations",
    [string]$Config = "configs/chorale_soprano_to_satb.yaml",
    [string]$Checkpoint = "",
    [ValidateSet("soprano_to_satb", "bass_to_satb", "masked_infill", "auto")]
    [string]$Task = "soprano_to_satb",
    [ValidateSet("soprano", "alto", "tenor", "bass")]
    [string]$InputRole = "soprano",
    [string]$KnownVoices = "",
    [string]$Prefix = "",
    [switch]$RenderAudio,
    [string]$AudioBackend = "additive",
    [switch]$NoRuleGuided,
    [switch]$NoSymbolicRepair,
    [switch]$NoFinalCadenceRepair,
    [int]$RepairPasses = 12,
    [double]$MaxViolationsPer100 = 12.0,
    [int]$MaxTotalViolations = 24,
    [double]$MaxTotalPenalty = 20.0,
    [int]$MaxSeventhResolutionViolations = 12,
    [switch]$RequireAudioForQuality
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot\common_project_python.ps1"

$argsList = @(
    "-m", "chorale.harmonize",
    "--input", $InputMusicXml,
    "--output-dir", $OutputDir,
    "--task", $Task,
    "--input-role", $InputRole
)

if ($Config) {
    $argsList += @("--config", $Config)
}
if ($Checkpoint) {
    $argsList += @("--checkpoint", $Checkpoint)
}
if ($KnownVoices) {
    $argsList += @("--known-voices", $KnownVoices)
}
if ($Prefix) {
    $argsList += @("--prefix", $Prefix)
}
if ($RenderAudio) {
    $argsList += "--render-audio"
    $argsList += @("--audio-backend", $AudioBackend)
}
if ($NoRuleGuided) {
    $argsList += "--no-rule-guided"
}
if ($NoSymbolicRepair) {
    $argsList += "--no-symbolic-repair"
}
if ($NoFinalCadenceRepair) {
    $argsList += "--no-final-cadence-repair"
}
$argsList += @("--repair-passes", "$RepairPasses")
$argsList += @("--max-violations-per-100", "$MaxViolationsPer100")
$argsList += @("--max-total-violations", "$MaxTotalViolations")
$argsList += @("--max-total-penalty", "$MaxTotalPenalty")
$argsList += @("--max-seventh-resolution-violations", "$MaxSeventhResolutionViolations")
if ($RequireAudioForQuality) {
    $argsList += "--require-audio-for-quality"
}

Write-Host "Harmonizing user MusicXML into score-level SATB output..."
Write-Host "InputMusicXml: $InputMusicXml"
Write-Host "OutputDir: $OutputDir"
Write-Host "Task: $Task"
Write-Host "Quality thresholds: violations/100 <= $MaxViolationsPer100, total violations <= $MaxTotalViolations, total penalty <= $MaxTotalPenalty"

Invoke-ProjectPython $argsList
