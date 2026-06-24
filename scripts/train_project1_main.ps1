$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

Invoke-ProjectPython @("-m", "chorale.data.build_dataset", "--config", "configs/chorale_main.yaml")
Invoke-ProjectPython @("-m", "chorale.train", "--config", "configs/chorale_main.yaml")
Invoke-ProjectPython @("-m", "chorale.evaluate", "--config", "configs/chorale_main.yaml", "--checkpoint", "runs/chorale_main/best.pt", "--output", "results/main_metrics.json")
Invoke-ProjectPython @("-m", "chorale.generate", "--config", "configs/chorale_main.yaml", "--checkpoint", "runs/chorale_main/best.pt", "--output-dir", "generated_scores", "--num-samples", "10", "--prefix", "main")
