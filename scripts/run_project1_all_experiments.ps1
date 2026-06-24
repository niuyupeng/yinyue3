param(
    [switch]$CpuDebug
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

if ($CpuDebug) {
    Write-Warning "CPU debug mode enabled. Use scripts/smoke_project1.ps1 for normal CPU validation; this is not a full RTX experiment."
} else {
    & "$PSScriptRoot\check_cuda.ps1" -RequireCuda
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$GeneratedDir = "generated_scores/project1_$Stamp"
$ExpertDir = "expert_eval/project1/$Stamp"

$Configs = @(
    @{ Config = "configs/chorale_rule_guided_decoding.yaml"; Run = "runs/chorale_rule_guided_decoding"; Output = "results/rule_guided_decoding_metrics.json"; Prefix = "rule_guided_decoding" },
    @{ Config = "configs/chorale_transformer_no_constraints.yaml"; Run = "runs/chorale_transformer_no_constraints"; Output = "results/transformer_no_constraints_metrics.json"; Prefix = "transformer_no_constraints" },
    @{ Config = "configs/chorale_lstm.yaml"; Run = "runs/chorale_lstm"; Output = "results/lstm_metrics.json"; Prefix = "lstm" },
    @{ Config = "configs/chorale_masked_infilling.yaml"; Run = "runs/chorale_masked_infilling"; Output = "results/masked_infilling_metrics.json"; Prefix = "masked_infilling" },
    @{ Config = "configs/chorale_soprano_to_satb.yaml"; Run = "runs/chorale_soprano_to_satb"; Output = "results/soprano_to_satb_metrics.json"; Prefix = "soprano_to_satb" }
)

Invoke-ProjectPython @("-m", "chorale.data.build_dataset", "--config", "configs/chorale_main.yaml")

foreach ($Experiment in $Configs) {
    Invoke-ProjectPython @("-m", "chorale.train", "--config", $Experiment.Config)
    Invoke-ProjectPython @("-m", "chorale.evaluate", "--config", $Experiment.Config, "--checkpoint", "$($Experiment.Run)/best.pt", "--output", $Experiment.Output)
    Invoke-ProjectPython @("-m", "chorale.generate", "--config", $Experiment.Config, "--checkpoint", "$($Experiment.Run)/best.pt", "--output-dir", $GeneratedDir, "--num-samples", "10", "--prefix", $Experiment.Prefix)
}

Invoke-ProjectPython @("-m", "chorale.generate", "--config", "configs/chorale_main.yaml", "--output-dir", $GeneratedDir, "--num-samples", "10", "--prefix", "rule_baseline")
Invoke-ProjectPython @("-m", "chorale.make_tables", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/tables")
Invoke-ProjectPython @("-m", "chorale.plot_results", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/figures")
Invoke-ProjectPython @("-m", "chorale.prepare_expert_eval", "--config", "configs/chorale_rule_guided_decoding.yaml", "--checkpoint", "runs/chorale_rule_guided_decoding/best.pt", "--num-samples", "10", "--output-dir", $ExpertDir)

Write-Host "All Project 1 experiments complete. See results/project1_metrics.csv and paper/tables/."
Write-Host "Generated MusicXML folder: $GeneratedDir"
Write-Host "Expert evaluation folder: $ExpertDir"
