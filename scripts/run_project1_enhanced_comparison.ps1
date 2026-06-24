param(
    [switch]$RebuildDataset,
    [switch]$RetrainBaselines,
    [switch]$IncludeAblations,
    [switch]$CpuDebug
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

if ($CpuDebug) {
    Write-Warning "CPU debug mode enabled. This is not a full RTX 4060 Ti experiment."
} else {
    & "$PSScriptRoot\check_cuda.ps1" -RequireCuda
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$GeneratedDir = "generated_scores/project1_enhanced_$Stamp"
$ExpertDir = "expert_eval/project1/enhanced_$Stamp"
$LogDir = "logs/project1_enhanced_$Stamp"
New-Item -ItemType Directory -Force -Path $GeneratedDir, $ExpertDir, $LogDir | Out-Null

function Invoke-LoggedProjectPython {
    param(
        [string[]]$PythonArgs,
        [string]$LogName
    )
    $logPath = Join-Path $LogDir $LogName
    Write-Host "python $($PythonArgs -join ' ')" | Tee-Object -FilePath $logPath -Append
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        Invoke-ProjectPython -PythonArgs $PythonArgs 2>&1 |
            ForEach-Object { $_.ToString() } |
            Tee-Object -FilePath $logPath -Append
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
    if ($exitCode -ne 0) {
        throw "Python command failed: $($PythonArgs -join ' ')"
    }
}

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
        Invoke-LoggedProjectPython @("-m", "chorale.train", "--config", $Config, "--run-dir", $RunDir) "$Prefix.train.log"
    }

    if (-not (Test-Path $Checkpoint)) {
        throw "Expected checkpoint was not created: $Checkpoint"
    }

    Write-Host "Evaluating: $Config with $Checkpoint"
    Invoke-LoggedProjectPython @("-m", "chorale.evaluate", "--config", $Config, "--checkpoint", $Checkpoint, "--output", $OutputJson) "$Prefix.evaluate.log"

    Write-Host "Generating MusicXML: $Prefix"
    Invoke-LoggedProjectPython @("-m", "chorale.generate", "--config", $Config, "--checkpoint", $Checkpoint, "--output-dir", $GeneratedDir, "--num-samples", "10", "--prefix", $Prefix) "$Prefix.generate.log"
}

if ($RebuildDataset -or -not (Test-Path "data/processed/chorale_main.npz")) {
    Invoke-LoggedProjectPython @("-m", "chorale.data.build_dataset", "--config", "configs/chorale_main.yaml") "dataset_build.log"
} else {
    Write-Host "Using existing processed dataset: data/processed/chorale_main.npz"
}

$BaselineSkip = -not $RetrainBaselines

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_lstm.yaml" `
    -RunDir "runs/chorale_lstm_full_20260615_085410" `
    -OutputJson "results/lstm_metrics.json" `
    -Prefix "lstm" `
    -SkipTrainingIfCheckpointExists:$BaselineSkip

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_transformer_no_constraints.yaml" `
    -RunDir "runs/chorale_transformer_no_constraints" `
    -OutputJson "results/transformer_no_constraints_metrics.json" `
    -Prefix "transformer_no_constraints" `
    -SkipTrainingIfCheckpointExists:$BaselineSkip

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_rule_guided_decoding.yaml" `
    -RunDir "runs/chorale_rule_guided_decoding_enhanced_$Stamp" `
    -OutputJson "results/rule_guided_decoding_enhanced_metrics.json" `
    -Prefix "rule_guided_decoding_enhanced"

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_masked_infilling.yaml" `
    -RunDir "runs/chorale_masked_infilling_enhanced_$Stamp" `
    -OutputJson "results/masked_infilling_enhanced_metrics.json" `
    -Prefix "masked_infilling_enhanced"

Run-TrainEvaluateGenerate `
    -Config "configs/chorale_soprano_to_satb.yaml" `
    -RunDir "runs/chorale_soprano_to_satb_enhanced_$Stamp" `
    -OutputJson "results/soprano_to_satb_enhanced_metrics.json" `
    -Prefix "soprano_to_satb_enhanced"

if ($IncludeAblations) {
    Run-TrainEvaluateGenerate `
        -Config "configs/chorale_ablation_no_harmony.yaml" `
        -RunDir "runs/chorale_ablation_no_harmony_enhanced_$Stamp" `
        -OutputJson "results/ablation_no_harmony_enhanced_metrics.json" `
        -Prefix "ablation_no_harmony_enhanced"

    Run-TrainEvaluateGenerate `
        -Config "configs/chorale_ablation_no_iterative_refinement.yaml" `
        -RunDir "runs/chorale_ablation_no_iterative_refinement_enhanced_$Stamp" `
        -OutputJson "results/ablation_no_iterative_refinement_enhanced_metrics.json" `
        -Prefix "ablation_no_iterative_refinement_enhanced"

    Run-TrainEvaluateGenerate `
        -Config "configs/chorale_ablation_no_rule_guided_decoding.yaml" `
        -RunDir "runs/chorale_ablation_no_rule_guided_decoding_enhanced_$Stamp" `
        -OutputJson "results/ablation_no_rule_guided_decoding_enhanced_metrics.json" `
        -Prefix "ablation_no_rule_guided_decoding_enhanced"

    Run-TrainEvaluateGenerate `
        -Config "configs/chorale_ablation_no_voice_relation.yaml" `
        -RunDir "runs/chorale_ablation_no_voice_relation_enhanced_$Stamp" `
        -OutputJson "results/ablation_no_voice_relation_enhanced_metrics.json" `
        -Prefix "ablation_no_voice_relation_enhanced"
}

Invoke-LoggedProjectPython @("-m", "chorale.make_tables", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/tables") "make_tables.log"
Invoke-LoggedProjectPython @("-m", "chorale.plot_results", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/figures") "plot_results.log"
Invoke-LoggedProjectPython @("-m", "chorale.prepare_expert_eval", "--config", "configs/chorale_rule_guided_decoding.yaml", "--checkpoint", "runs/chorale_rule_guided_decoding_enhanced_$Stamp/best.pt", "--num-samples", "10", "--output-dir", $ExpertDir) "prepare_expert_eval.log"

Write-Host "Enhanced Project 1 comparison complete."
Write-Host "Stamp: $Stamp"
Write-Host "Logs: $LogDir"
Write-Host "Generated MusicXML folder: $GeneratedDir"
Write-Host "Expert evaluation folder: $ExpertDir"
