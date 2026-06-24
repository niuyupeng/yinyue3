param(
    [int]$PollSeconds = 30
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

& "$PSScriptRoot\check_cuda.ps1" -RequireCuda

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$GeneratedDir = "generated_scores/project1_resume_$Stamp"
$ExpertDir = "expert_eval/project1/resume_$Stamp"

function Wait-ForConfigTraining {
    param(
        [string]$ConfigPath
    )
    while ($true) {
        $matches = Get-CimInstance Win32_Process | Where-Object {
            $_.Name -match "python" -and
            $_.CommandLine -match "chorale\.train" -and
            $_.CommandLine -match [regex]::Escape($ConfigPath)
        }
        if (-not $matches) {
            break
        }
        Write-Host "Waiting for active training to finish: $ConfigPath"
        Start-Sleep -Seconds $PollSeconds
    }
}

function Run-EvaluateGenerate {
    param(
        [string]$Config,
        [string]$RunDir,
        [string]$OutputJson,
        [string]$Prefix
    )
    $Checkpoint = "$RunDir/best.pt"
    if (-not (Test-Path $Checkpoint)) {
        Invoke-ProjectPython @("-m", "chorale.train", "--config", $Config)
    }
    Invoke-ProjectPython @("-m", "chorale.evaluate", "--config", $Config, "--checkpoint", $Checkpoint, "--output", $OutputJson)
    Invoke-ProjectPython @("-m", "chorale.generate", "--config", $Config, "--checkpoint", $Checkpoint, "--output-dir", $GeneratedDir, "--num-samples", "10", "--prefix", $Prefix)
}

Wait-ForConfigTraining "configs/chorale_lstm.yaml"

Run-EvaluateGenerate "configs/chorale_lstm.yaml" "runs/chorale_lstm" "results/lstm_metrics.json" "lstm"
Run-EvaluateGenerate "configs/chorale_transformer_no_constraints.yaml" "runs/chorale_transformer_no_constraints" "results/transformer_no_constraints_metrics.json" "transformer_no_constraints"
Run-EvaluateGenerate "configs/chorale_rule_guided_decoding.yaml" "runs/chorale_rule_guided_decoding" "results/rule_guided_decoding_metrics.json" "rule_guided_decoding"
Run-EvaluateGenerate "configs/chorale_masked_infilling.yaml" "runs/chorale_masked_infilling" "results/masked_infilling_metrics.json" "masked_infilling"
Run-EvaluateGenerate "configs/chorale_soprano_to_satb.yaml" "runs/chorale_soprano_to_satb" "results/soprano_to_satb_metrics.json" "soprano_to_satb"

Invoke-ProjectPython @("-m", "chorale.generate", "--config", "configs/chorale_main.yaml", "--output-dir", $GeneratedDir, "--num-samples", "10", "--prefix", "rule_baseline")
Invoke-ProjectPython @("-m", "chorale.make_tables", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/tables")
Invoke-ProjectPython @("-m", "chorale.plot_results", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/figures")
Invoke-ProjectPython @("-m", "chorale.prepare_expert_eval", "--config", "configs/chorale_rule_guided_decoding.yaml", "--checkpoint", "runs/chorale_rule_guided_decoding/best.pt", "--num-samples", "10", "--output-dir", $ExpertDir)

Write-Host "Project 1 resume pipeline complete."
Write-Host "Generated MusicXML folder: $GeneratedDir"
Write-Host "Expert evaluation folder: $ExpertDir"
