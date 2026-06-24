function Invoke-ProjectPython {
    param(
        [string[]]$PythonArgs
    )

    if (Test-Path ".\.venv\Scripts\python.exe") {
        & ".\.venv\Scripts\python.exe" @PythonArgs
    } else {
        $UsedLauncher = $false
        try {
            & py -3.11 --version *> $null
            if ($LASTEXITCODE -eq 0) {
                & py -3.11 @PythonArgs
                $UsedLauncher = $true
            }
        } catch {
            $UsedLauncher = $false
        }
        if (-not $UsedLauncher) {
            try {
                & py -3.10 --version *> $null
                if ($LASTEXITCODE -eq 0) {
                    & py -3.10 @PythonArgs
                    $UsedLauncher = $true
                }
            } catch {
                $UsedLauncher = $false
            }
        }
        if (-not $UsedLauncher) {
            & python @PythonArgs
        }
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($PythonArgs -join ' ')"
    }
}
