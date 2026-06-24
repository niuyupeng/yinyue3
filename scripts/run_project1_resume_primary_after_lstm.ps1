param(
    [string]$LstmRunDir = "runs/chorale_lstm_full_20260615_085410"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

& "$PSScriptRoot\check_cuda.ps1" -RequireCuda

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$GeneratedDir = "generated_scores/project1_primary_resume_$Stamp"
$ExpertDir = "expert_eval/project1/primary_resume_$Stamp"

function Assert-Checkpoint {
    param(
        [string]$Checkpoint
    )
    if (-not (Test-Path $Checkpoint)) {
        throw "Required checkpoint not found: $Checkpoint"
    }
}

function Train-IfNeeded {
    param(
        [string]$Config,
        [string]$RunDir
    )
    $Checkpoint = "$RunDir/best.pt"
    if (Test-Path $Checkpoint) {
        Write-Host "Using existing checkpoint: $Checkpoint"
        return
    }
    Invoke-ProjectPython @("-m", "chorale.train", "--config", $Config, "--run-dir", $RunDir)
    Assert-Checkpoint $Checkpoint
}

function Evaluate-Generate {
    param(
        [string]$Config,
        [string]$RunDir,
        [string]$OutputJson,
        [string]$Prefix
    )
    $Checkpoint = "$RunDir/best.pt"
    Assert-Checkpoint $Checkpoint
    Invoke-ProjectPython @("-m", "chorale.evaluate", "--config", $Config, "--checkpoint", $Checkpoint, "--output", $OutputJson)
    Invoke-ProjectPython @("-m", "chorale.generate", "--config", $Config, "--checkpoint", $Checkpoint, "--output-dir", $GeneratedDir, "--num-samples", "10", "--prefix", $Prefix)
}

if (-not (Test-Path "data/processed/chorale_main.npz")) {
    Invoke-ProjectPython @("-m", "chorale.data.build_dataset", "--config", "configs/chorale_main.yaml")
} else {
    Write-Host "Using existing processed dataset: data/processed/chorale_main.npz"
}

Evaluate-Generate "configs/chorale_lstm.yaml" $LstmRunDir "results/lstm_metrics.json" "lstm"

Train-IfNeeded "configs/chorale_masked_infilling.yaml" "runs/chorale_masked_infilling"
Evaluate-Generate "configs/chorale_masked_infilling.yaml" "runs/chorale_masked_infilling" "results/masked_infilling_metrics.json" "masked_infilling"

Train-IfNeeded "configs/chorale_soprano_to_satb.yaml" "runs/chorale_soprano_to_satb"
Evaluate-Generate "configs/chorale_soprano_to_satb.yaml" "runs/chorale_soprano_to_satb" "results/soprano_to_satb_metrics.json" "soprano_to_satb"

Invoke-ProjectPython @("-m", "chorale.make_tables", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/tables")
Invoke-ProjectPython @("-m", "chorale.plot_results", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/figures")
Invoke-ProjectPython @("-m", "chorale.prepare_expert_eval", "--config", "configs/chorale_rule_guided_decoding.yaml", "--checkpoint", "runs/chorale_rule_guided_decoding/best.pt", "--num-samples", "10", "--output-dir", $ExpertDir)

Write-Host "Primary Project 1 resume complete."
Write-Host "Generated MusicXML folder: $GeneratedDir"
Write-Host "Expert evaluation folder: $ExpertDir"
