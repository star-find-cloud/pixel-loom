$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    Write-Host 'Ready. Run launch.ps1. Generate MCP configuration with .venv\Scripts\pixel-loom-config.exe.'
} finally {
    Pop-Location
}
