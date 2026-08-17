$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $Root
try {
    $Config = "configs\cih_s2s_cpu_smoke.yaml"
    $Checkpoint = "runs\cih_s2s_cpu_smoke\best.pt"
    & .\.venv\Scripts\python.exe -m pip install -e . | Out-Host
    & .\.venv\Scripts\python.exe scripts\check_hardware.py --config $Config --out results\cih_s2s_cpu_smoke_hardware_check.json | Out-Host
    & .\.venv\Scripts\python.exe -m chorale.data.build_dataset --config $Config | Out-Host
    & .\.venv\Scripts\python.exe -m chorale.train --config $Config --fast-dev-run | Out-Host
    & .\.venv\Scripts\python.exe -m chorale.evaluate --config $Config --checkpoint $Checkpoint --output results\cih_s2s_cpu_smoke_metrics.json --no-project1-outputs | Out-Host
    & .\.venv\Scripts\python.exe -m chorale.generate --config $Config --checkpoint $Checkpoint --output-dir generated_scores\cih_s2s_cpu_smoke --num-samples 1 --prefix cih_s2s_cpu_smoke | Out-Host
    & .\.venv\Scripts\python.exe scripts\make_paper_figures.py --root . | Out-Host
    Write-Host "CIH-S2S smoke test completed. Smoke metrics are software validation only."
}
finally {
    Pop-Location
}
