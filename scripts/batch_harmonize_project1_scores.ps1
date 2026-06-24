param(
    [Parameter(Mandatory=$true)]
    [string]$InputDir,
    [string]$OutputDir = "generated_scores/batch_user_harmonizations",
    [string]$Config = "configs/chorale_soprano_to_satb.yaml",
    [string]$Checkpoint = "",
    [ValidateSet("soprano_to_satb", "bass_to_satb", "masked_infill", "auto")]
    [string]$Task = "soprano_to_satb",
    [ValidateSet("soprano", "alto", "tenor", "bass")]
    [string]$InputRole = "soprano",
    [string]$KnownVoices = "",
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
    [switch]$RequireAudioForQuality,
    [switch]$Recursive,
    [switch]$StopOnError,
    [int]$Limit = 0
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot\common_project_python.ps1"

$argsList = @(
    "-m", "chorale.batch_harmonize",
    "--input-dir", $InputDir,
    "--output-dir", $OutputDir,
    "--task", $Task,
    "--input-role", $InputRole,
    "--repair-passes", "$RepairPasses",
    "--max-violations-per-100", "$MaxViolationsPer100",
    "--max-total-violations", "$MaxTotalViolations",
    "--max-total-penalty", "$MaxTotalPenalty",
    "--max-seventh-resolution-violations", "$MaxSeventhResolutionViolations"
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
if ($RequireAudioForQuality) {
    $argsList += "--require-audio-for-quality"
}
if ($Recursive) {
    $argsList += "--recursive"
}
if ($StopOnError) {
    $argsList += "--stop-on-error"
}
if ($Limit -gt 0) {
    $argsList += @("--limit", "$Limit")
}

Write-Host "Batch harmonizing user MusicXML files into score-level SATB outputs..."
Write-Host "InputDir: $InputDir"
Write-Host "OutputDir: $OutputDir"
Write-Host "Task: $Task"
Write-Host "Quality thresholds: violations/100 <= $MaxViolationsPer100, total violations <= $MaxTotalViolations, total penalty <= $MaxTotalPenalty"

Invoke-ProjectPython $argsList
