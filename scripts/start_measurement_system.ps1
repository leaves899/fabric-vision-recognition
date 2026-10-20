param([ValidateRange(1024, 65535)][int]$Port = 8018)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$existingService = $null
try { $existingService = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2 } catch { }
if ($existingService.version -like 'report-system-*') {
    Start-Process "http://127.0.0.1:$Port"
    return
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already used by another service. Choose -Port with an unused port."
}
$venvPython = Join-Path $projectRoot '.venv-measurement\Scripts\python.exe'
$pythonCommand = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }
& $pythonCommand -c 'import fastapi, uvicorn, multipart, numpy, cv2, scipy, PIL; from pydantic import model_validator' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing local image recognition dependencies...'
    python -m venv (Join-Path $projectRoot '.venv-measurement')
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed' }
    $pythonCommand = $venvPython
    & $pythonCommand -m pip install -r (Join-Path $projectRoot 'fabric_measurement\requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
Write-Host "Open http://127.0.0.1:$Port  |  Ctrl+C to stop"
$browserJob = Start-Job -ArgumentList $Port -ScriptBlock {
    param($ServicePort)
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $service = Invoke-RestMethod -Uri "http://127.0.0.1:$ServicePort/api/health" -TimeoutSec 1
            if ($service.status -eq 'ok') { Start-Process "http://127.0.0.1:$ServicePort"; break }
        } catch { }
        Start-Sleep -Milliseconds 400
    }
}
try {
    & $pythonCommand -m uvicorn fabric_measurement.server:app --host 127.0.0.1 --port $Port
    $serverExitCode = $LASTEXITCODE
} finally {
    Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue
}
exit $serverExitCode
