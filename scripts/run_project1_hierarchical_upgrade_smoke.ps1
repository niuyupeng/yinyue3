$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

$Config = "configs/chorale_hierarchical_score_transformer_smoke.yaml"
$RunDir = "runs/chorale_hierarchical_score_transformer_smoke"
$MetricsJson = "results/hierarchical_score_transformer_smoke_metrics.json"
$GeneratedDir = "generated_scores/hierarchical_score_transformer_smoke"

Invoke-ProjectPython @("-m", "pip", "install", "-e", ".", "--no-build-isolation")
Invoke-ProjectPython @("-m", "chorale.data.build_dataset", "--config", $Config, "--max-chorales", "20")
Invoke-ProjectPython @("-m", "chorale.train", "--config", $Config, "--fast-dev-run")
Invoke-ProjectPython @(
    "-m", "chorale.evaluate",
    "--config", $Config,
    "--checkpoint", "$RunDir/best.pt",
    "--output", $MetricsJson,
    "--no-project1-outputs"
)
Invoke-ProjectPython @(
    "-m", "chorale.generate",
    "--config", $Config,
    "--checkpoint", "$RunDir/best.pt",
    "--output-dir", $GeneratedDir,
    "--num-samples", "1",
    "--prefix", "hierarchical_smoke"
)

Write-Host "Hierarchical score-to-score smoke complete."
Write-Host "Metrics: $MetricsJson"
Write-Host "Generated MusicXML: $GeneratedDir"
