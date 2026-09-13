param(
    [switch]$Html,
    [switch]$TotalOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Undertow's virtual environment was not found at $Python. Create it, then install requirements.txt."
}

function Invoke-CoverageCommand {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$CoverageArguments
    )

    & $Python -m coverage @CoverageArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Coverage command failed with exit code $LASTEXITCODE."
    }
}

if ($Html -and $TotalOnly) {
    throw "Choose either -Html or -TotalOnly."
}

Push-Location $ProjectRoot
try {
    Invoke-CoverageCommand erase
    Invoke-CoverageCommand run --source=undertow -m unittest discover -s tests -v
    if ($TotalOnly) {
        Invoke-CoverageCommand report --format=total
        return
    }

    Invoke-CoverageCommand report --show-missing
    if ($Html) {
        Invoke-CoverageCommand html
        Write-Host "HTML report written to htmlcov\\index.html"
    }
}
finally {
    Pop-Location
}
