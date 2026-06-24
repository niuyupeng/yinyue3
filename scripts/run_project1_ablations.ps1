param(
    [switch]$RebuildDataset
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

& "$PSScriptRoot\check_cuda.ps1" -RequireCuda

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$GeneratedDir = "generated_scores/project1_ablations_$Stamp"

if ($RebuildDataset -or -not (Test-Path "data/processed/chorale_main.npz")) {
    Invoke-ProjectPython @("-m", "chorale.data.build_dataset", "--config", "configs/chorale_main.yaml")
} else {
    Write-Host "Using existing processed dataset: data/processed/chorale_main.npz"
}

$Configs = @(
    @{ Config = "configs/chorale_ablation_no_harmony.yaml"; Run = "runs/chorale_ablation_no_harmony"; Output = "results/ablation_no_harmony_metrics.json"; Prefix = "ablation_no_harmony" },
    @{ Config = "configs/chorale_ablation_no_iterative_refinement.yaml"; Run = "runs/chorale_ablation_no_iterative_refinement"; Output = "results/ablation_no_iterative_refinement_metrics.json"; Prefix = "ablation_no_iterative_refinement" },
    @{ Config = "configs/chorale_ablation_no_rule_guided_decoding.yaml"; Run = "runs/chorale_ablation_no_rule_guided_decoding"; Output = "results/ablation_no_rule_guided_decoding_metrics.json"; Prefix = "ablation_no_rule_guided_decoding" }
)

foreach ($Experiment in $Configs) {
    $Checkpoint = "$($Experiment.Run)/best.pt"
    if (-not (Test-Path $Checkpoint)) {
        Invoke-ProjectPython @("-m", "chorale.train", "--config", $Experiment.Config)
    } else {
        Write-Host "Using existing checkpoint: $Checkpoint"
    }
    Invoke-ProjectPython @("-m", "chorale.evaluate", "--config", $Experiment.Config, "--checkpoint", $Checkpoint, "--output", $Experiment.Output)
    Invoke-ProjectPython @("-m", "chorale.generate", "--config", $Experiment.Config, "--checkpoint", $Checkpoint, "--output-dir", $GeneratedDir, "--num-samples", "10", "--prefix", $Experiment.Prefix)
}

Invoke-ProjectPython @("-m", "chorale.make_tables", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/tables")
Invoke-ProjectPython @("-m", "chorale.plot_results", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/figures")

Write-Host "Project 1 ablations complete."
Write-Host "Generated MusicXML folder: $GeneratedDir"
