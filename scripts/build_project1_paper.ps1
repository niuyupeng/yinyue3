param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PaperDir = Join-Path $Root "paper"

if (-not (Test-Path -LiteralPath (Join-Path $PaperDir "main_submission.tex"))) {
    throw "Missing paper main_submission.tex at $PaperDir"
}

Push-Location $PaperDir
try {
    if ($Clean) {
        $buildFiles = @("main_submission.aux", "main_submission.bbl", "main_submission.blg", "main_submission.log", "main_submission.out", "main_submission.pdf", "main_submission.toc")
        foreach ($file in $buildFiles) {
            if (Test-Path -LiteralPath $file) {
                Remove-Item -LiteralPath $file -Force
            }
        }
    }

    & xelatex -interaction=nonstopmode -halt-on-error main_submission.tex
    if ($LASTEXITCODE -ne 0) { throw "First XeLaTeX pass failed." }

    & bibtex main_submission
    if ($LASTEXITCODE -ne 0) { throw "BibTeX pass failed." }

    & xelatex -interaction=nonstopmode -halt-on-error main_submission.tex
    if ($LASTEXITCODE -ne 0) { throw "Second XeLaTeX pass failed." }

    & xelatex -interaction=nonstopmode -halt-on-error main_submission.tex
    if ($LASTEXITCODE -ne 0) { throw "Final XeLaTeX pass failed." }

    if (-not (Test-Path -LiteralPath "main_submission.pdf")) {
        throw "The manuscript did not produce main_submission.pdf."
    }

    Write-Host "Manuscript built: $PaperDir\main_submission.pdf"
}
finally {
    Pop-Location
}
