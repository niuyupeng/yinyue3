$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

Invoke-ProjectPython @("-m", "pip", "install", "-r", "requirements.txt")
Invoke-ProjectPython @("-m", "pip", "install", "-e", ".", "--no-build-isolation")
Invoke-ProjectPython @("-m", "chorale.data.build_dataset", "--config", "configs/chorale_smoke.yaml", "--max-chorales", "20")
Invoke-ProjectPython @("-m", "pytest", "-q")
Invoke-ProjectPython @("-m", "chorale.train", "--config", "configs/chorale_smoke.yaml", "--fast-dev-run")
Invoke-ProjectPython @("-m", "chorale.evaluate", "--config", "configs/chorale_smoke.yaml", "--checkpoint", "runs/chorale_smoke/best.pt", "--output", "results/smoke_metrics.json")
Invoke-ProjectPython @("-m", "chorale.generate", "--config", "configs/chorale_smoke.yaml", "--checkpoint", "runs/chorale_smoke/best.pt", "--output-dir", "generated_scores", "--num-samples", "2", "--prefix", "smoke")
Invoke-ProjectPython @("-m", "chorale.make_tables", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/tables")
Invoke-ProjectPython @("-m", "chorale.plot_results", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/figures")

Write-Host "Smoke project complete. Metrics: results/smoke_metrics.json"
