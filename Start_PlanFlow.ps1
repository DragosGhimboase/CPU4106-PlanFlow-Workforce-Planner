$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    & py -3 -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) {
        throw 'Python setup failed. Install Python 3.11 or newer.'
    }
}
& $taskPython -c 'import importlib.util, sys; sys.exit(not all(map(importlib.util.find_spec, sys.argv[1:])))' pip
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Preparing pip in the project Python environment...'
    & $taskPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare pip. Repair the Python installation, then start PlanFlow again.' }
}
& $taskPython -c 'import importlib.util, sys; sys.exit(not all(map(importlib.util.find_spec, sys.argv[1:])))' flask pymysql cryptography
if ($LASTEXITCODE -ne 0) {
    & $taskPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection.' }
}
$env:PLANFLOW_PORT = '8765'
$env:PLANFLOW_OPEN_BROWSER = '1'
Write-Host 'PlanFlow opens at http://127.0.0.1:8765'
Write-Host 'Keep this terminal open. Press Ctrl+C to stop the app.'
& $taskPython (Join-Path $PSScriptRoot 'app.py')
