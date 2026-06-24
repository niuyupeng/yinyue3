$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common_project_python.ps1"

Invoke-ProjectPython @("-m", "chorale.make_tables", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/tables")
Invoke-ProjectPython @("-m", "chorale.plot_results", "--metrics-csv", "results/project1_metrics.csv", "--output-dir", "paper/figures")
& "$PSScriptRoot\summarize_project1_expert_ratings.ps1" -RatingsDir "expert_eval/project1/returned_ratings" -OutDir "results" -AllowPreliminary
if ($LASTEXITCODE -ne 0) {
    throw "Expert-rating table refresh failed."
}
Write-Host "Updated project tables and figures."
