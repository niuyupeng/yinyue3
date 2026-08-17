param(
    [string]$Config = "configs\cih_s2s_4060ti_16gb.yaml",
    [switch]$FastDevRun
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $Root
try {
    if ($FastDevRun) {
        & .\.venv\Scripts\python.exe -m chorale.train --config $Config --fast-dev-run
    }
    else {
        & .\.venv\Scripts\python.exe -m chorale.train --config $Config
    }
}
finally {
    Pop-Location
}
