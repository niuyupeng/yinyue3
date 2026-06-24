$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

Invoke-ProjectPython @("-m", "chorale.data.build_dataset", "--config", "configs/chorale_main.yaml")
Invoke-ProjectPython @("-m", "chorale.train", "--config", "configs/chorale_lstm.yaml")
Invoke-ProjectPython @("-m", "chorale.evaluate", "--config", "configs/chorale_lstm.yaml", "--checkpoint", "runs/chorale_lstm/best.pt", "--output", "results/lstm_metrics.json")
Invoke-ProjectPython @("-m", "chorale.generate", "--config", "configs/chorale_lstm.yaml", "--checkpoint", "runs/chorale_lstm/best.pt", "--output-dir", "generated_scores", "--num-samples", "10", "--prefix", "lstm")

Write-Host "RuleBaseline is implemented in src/chorale/models/rule_baseline.py and is used by generate.py when no checkpoint is supplied."
