param(
    [switch]$UseExistingLstm,
    [switch]$RebuildDataset
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

& "$PSScriptRoot\check_cuda.ps1" -RequireCuda

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$GeneratedDir = "generated_scores/project1_remaining_$Stamp"
$ExpertDir = "expert_eval/project1/remaining_$Stamp"
$LstmRunDir = if ($UseExistingLstm) { "runs/chorale_lstm" } else { "runs/chorale_lstm_full_$Stamp" }

function Run-TrainEvaluateGenerate {
    param(
        [string]$Config,
        [string]$RunDir,
        [string]$OutputJson,
        [string]$Prefix,
        [switch]$SkipTrainingIfCheckpointExists
    )

    $Checkpoint = "$RunDir/best.pt"
    if ($SkipTrainingIfCheckpointExists -and (Test-Path $Checkpoint)) {
        Write-Host "Using existing checkpoint: $Checkpoint"
    } else {
        Write-Host "Training: $Config -> $RunDir"
        Invoke-ProjectPython @("-m", "chorale.train", "--config", $Config, "--run-dir", $RunDir)
    }

    if (-not (Test-Path $Checkpoint)) {
        throw "Expected checkpoint was not created: $Checkpoint"
    }

    Write-Host "Evaluating: $Config with $Checkpoint"
    Invoke-ProjectPython @("-m", "chorale.evaluate", "--config", $Config, "--checkpoint", $Checkpoint, "--output", $OutputJson)

    Write-Host "Generating MusicXML: $Prefix"
    Invoke-ProjectPython @("-m", "chorale.generate", "--config", $Config, "--checkpoint", $Checkpoint, "--output-dir", $GeneratedDir, "--num-samples", "10", "--prefix", $Prefix)
}

if ($RebuildDataset -or -not (Test-Path "data/processed/chorale_main.npz")) {
    Invoke-ProjectPython @("-m", "chorale.data.build_dataset", "--config", "configs/chorale_main.yaml")
} else {
    Write-Host "Using existing processed dataset: data/processed/chorale_main.npz"
}

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_rule_guided_decoding.yaml" `
    -RunDir "runs/chorale_rule_guided_decoding" `
    -OutputJson "results/rule_guided_decoding_metrics.json" `
    -Prefix "rule_guided_decoding" `
    -SkipTrainingIfCheckpointExists

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_transformer_no_constraints.yaml" `
    -RunDir "runs/chorale_transformer_no_constraints" `
    -OutputJson "results/transformer_no_constraints_metrics.json" `
    -Prefix "transformer_no_constraints" `
    -SkipTrainingIfCheckpointExists

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_lstm.yaml" `
    -RunDir $LstmRunDir `
    -OutputJson "results/lstm_metrics.json" `
    -Prefix "lstm" `
    -SkipTrainingIfCheckpointExists:$UseExistingLstm

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_masked_infilling.yaml" `
    -RunDir "runs/chorale_masked_infilling" `
    -OutputJson "results/masked_infilling_metrics.json" `
    -Prefix "masked_infilling" `
    -SkipTrainingIfCheckpointExists

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_soprano_to_satb.yaml" `
    -RunDir "runs/chorale_soprano_to_satb" `
    -OutputJson "results/soprano_to_satb_metrics.json" `
    -Prefix "soprano_to_satb" `
    -SkipTrainingIfCheckpointExists

Invoke-ProjectPython @("-m", "chorale.make_tables", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/tables")
Invoke-ProjectPython @("-m", "chorale.plot_results", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/figures")
Invoke-ProjectPython @("-m", "chorale.prepare_expert_eval", "--config", "configs/chorale_rule_guided_decoding.yaml", "--checkpoint", "runs/chorale_rule_guided_decoding/best.pt", "--num-samples", "10", "--output-dir", $ExpertDir)

Write-Host "Remaining Project 1 experiments complete."
Write-Host "Generated MusicXML folder: $GeneratedDir"
Write-Host "Expert evaluation folder: $ExpertDir"
Write-Host "LSTM run folder: $LstmRunDir"
