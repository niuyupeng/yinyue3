param(
    [string]$Checkpoint = "runs/chorale_rule_guided_decoding_enhanced_20260616_205831/best.pt",
    [string]$BaseConfig = "configs/chorale_rule_guided_decoding.yaml",
    [int]$MaxBatches = 0,
    [int]$ExportSamples = 0
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing virtual environment Python: $Python"
}
if (-not (Test-Path $Checkpoint)) {
    throw "Missing checkpoint: $Checkpoint"
}

@'
import torch
print("torch:", torch.__version__)
print("cuda_available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("cuda_device:", torch.cuda.get_device_name(0))
else:
    raise SystemExit("CUDA is unavailable. This sweep is intended for the local RTX GPU; use --max-batches manually for CPU debug only.")
'@ | & $Python -

$ArgsList = @(
    "-m", "chorale.rerank_sweep",
    "--base-config", $BaseConfig,
    "--checkpoint", $Checkpoint,
    "--output-csv", "results/project1_rerank_sweep_latest.csv",
    "--output-json", "results/project1_rerank_sweep_latest.json",
    "--require-cuda"
)
if ($MaxBatches -gt 0) {
    $ArgsList += @("--max-batches", "$MaxBatches")
}
if ($ExportSamples -gt 0) {
    $ArgsList += @("--export-samples", "$ExportSamples")
}

& $Python @ArgsList
