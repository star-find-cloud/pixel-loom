$ErrorActionPreference = 'Stop'
$pixelPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pixelPython)) {
    $pixelPython = (Get-Command python -ErrorAction Stop).Source
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $pixelPython -c 'from pixel_workbench.lifecycle import ensure_editor; ensure_editor()'
    if ($LASTEXITCODE -ne 0) { throw 'Pixel Loom could not start. Run setup.ps1 and check the per-user PixelLoom runtime logs.' }
} finally {
    Pop-Location
}
