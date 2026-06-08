param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [switch]$UseVoicePython
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$LogsDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

function Test-PortFree {
    param([int]$Port)
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $Port)
    try {
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $listener.Stop()
    }
}

function Find-FreePort {
    param([int]$StartPort)
    for ($port = $StartPort; $port -lt ($StartPort + 200); $port++) {
        if (Test-PortFree -Port $port) {
            return $port
        }
    }
    throw "No free localhost port found from $StartPort."
}

function Resolve-Python {
    $voicePython = Join-Path $Root "voice_venv\Scripts\python.exe"
    if ($UseVoicePython -and (Test-Path $voicePython)) {
        return $voicePython
    }
    $localPython = Join-Path $ApiDir ".venv\Scripts\python.exe"
    if (Test-Path $localPython) {
        return $localPython
    }
    $systemPython = (Get-Command python -ErrorAction SilentlyContinue)
    if (-not $systemPython) {
        throw "Python was not found. Install Python 3.10+ and retry."
    }
    return $systemPython.Source
}

function Ensure-ApiVenv {
    $voicePython = Join-Path $Root "voice_venv\Scripts\python.exe"
    if ($UseVoicePython -and (Test-Path $voicePython)) {
        return $voicePython
    }

    $venvPython = Join-Path $ApiDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "Creating API virtual environment..."
        & python -m venv (Join-Path $ApiDir ".venv")
    }
    Write-Host "Installing/updating API dependencies..."
    & $venvPython -m pip install -e $ApiDir | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install API dependencies."
    }
    return $venvPython
}

$ApiPort = Find-FreePort -StartPort $ApiPort
$WebPort = Find-FreePort -StartPort $WebPort
$ApiPython = Ensure-ApiVenv
$WebPython = Resolve-Python

$env:PYTHONPATH = $ApiDir
if ($UseVoicePython -and (Test-Path "D:\CosyVoice")) {
    $env:OPENINTERVIEW_COSYVOICE_PATH = "D:\CosyVoice"
    $env:PYTHONPATH = "D:\CosyVoice;$env:PYTHONPATH"
}

$ffmpeg = Get-ChildItem (Join-Path $Root "tools\ffmpeg") -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ffmpeg) {
    $env:PATH = "$($ffmpeg.Directory.FullName);$env:PATH"
}

$ApiOut = Join-Path $LogsDir "api-local-$ApiPort.log"
$ApiErr = Join-Path $LogsDir "api-local-$ApiPort.err.log"
$WebOut = Join-Path $LogsDir "web-local-$WebPort.log"
$WebErr = Join-Path $LogsDir "web-local-$WebPort.err.log"

Write-Host "Starting OpenInterview API on http://127.0.0.1:$ApiPort ..."
Start-Process -FilePath $ApiPython `
    -ArgumentList @("-m", "uvicorn", "openinterview_api.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
    -WorkingDirectory $ApiDir `
    -RedirectStandardOutput $ApiOut `
    -RedirectStandardError $ApiErr `
    -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2
        if ($health.status -eq "ok") {
            break
        }
    } catch {
        if ((Get-Date) -gt $deadline) {
            throw "API did not become ready. See $ApiErr"
        }
    }
} while ($true)

Write-Host "Starting OpenInterview Web on http://127.0.0.1:$WebPort ..."
Start-Process -FilePath $WebPython `
    -ArgumentList @("-m", "http.server", "$WebPort", "--bind", "127.0.0.1") `
    -WorkingDirectory $WebDir `
    -RedirectStandardOutput $WebOut `
    -RedirectStandardError $WebErr `
    -WindowStyle Hidden

$Url = "http://127.0.0.1:$WebPort/?api=http://127.0.0.1:$ApiPort"
Write-Host ""
Write-Host "OpenInterview is ready."
Write-Host "Open this URL:"
Write-Host $Url
Write-Host ""
Write-Host "API log: $ApiOut"
Write-Host "Web log: $WebOut"
