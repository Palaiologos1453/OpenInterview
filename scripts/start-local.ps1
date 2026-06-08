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

function Write-Step {
    param([string]$Message)
    Write-Host "[OpenInterview] $Message"
}

function Write-Fix {
    param([string]$Message)
    Write-Host "  -> $Message" -ForegroundColor Yellow
}

function Test-PythonVersion {
    param([string]$PythonPath)
    $versionText = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $versionText) {
        throw "Python exists but cannot run: $PythonPath"
    }
    $parts = $versionText.Trim().Split(".")
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        throw "Python $versionText is too old. OpenInterview requires Python 3.10+."
    }
    return $versionText.Trim()
}

function Test-Pip {
    param([string]$PythonPath)
    & $PythonPath -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "pip is not available for $PythonPath. Reinstall Python and enable pip."
    }
}

function Show-StartupFailure {
    param([string]$Message)
    Write-Host ""
    Write-Host "OpenInterview failed to start." -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Common fixes:"
    Write-Fix "Install Python 3.10+ from https://www.python.org/downloads/ and check 'Add python.exe to PATH'."
    Write-Fix "If PowerShell blocks scripts, run: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned"
    Write-Fix "If dependency install is slow, try a faster pip mirror, then rerun this script."
    Write-Fix "If ports are occupied, rerun with custom ports: .\scripts\start-local.ps1 -ApiPort 8100 -WebPort 5200"
    Write-Fix "Check logs under: $LogsDir"
}

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
            if ($port -ne $StartPort) {
                Write-Step "Port $StartPort is occupied; using $port instead."
            }
            return $port
        }
    }
    throw "No free localhost port found from $StartPort."
}

function Wait-PortListening {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 10
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 300
        $connection = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($connection) {
            return
        }
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not start listening within $TimeoutSeconds seconds."
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
        throw "Python was not found in PATH."
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
        Write-Step "Creating API virtual environment..."
        & python -m venv (Join-Path $ApiDir ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create API virtual environment."
        }
    }
    $version = Test-PythonVersion -PythonPath $venvPython
    Test-Pip -PythonPath $venvPython
    Write-Step "Using Python $version for API."
    Write-Step "Installing/updating API dependencies..."
    & $venvPython -m pip install -e $ApiDir | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install API dependencies. See pip output above."
    }
    return $venvPython
}

try {
    Write-Step "Workspace: $Root"
    Write-Step "PowerShell $($PSVersionTable.PSVersion)"

    $systemPython = Resolve-Python
    $systemVersion = Test-PythonVersion -PythonPath $systemPython
    Write-Step "Found Python $systemVersion at $systemPython"

    $ApiPort = Find-FreePort -StartPort $ApiPort
    $WebPort = Find-FreePort -StartPort $WebPort
    $ApiPython = Ensure-ApiVenv
    $WebPython = Resolve-Python
    Test-PythonVersion -PythonPath $WebPython | Out-Null

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

    Write-Step "Starting API on http://127.0.0.1:$ApiPort ..."
    Start-Process -FilePath $ApiPython `
        -ArgumentList @("-m", "uvicorn", "openinterview_api.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
        -WorkingDirectory $ApiDir `
        -RedirectStandardOutput $ApiOut `
        -RedirectStandardError $ApiErr `
        -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2
            if ($health.status -eq "ok") {
                break
            }
        } catch {
            if ((Get-Date) -gt $deadline) {
                $tail = ""
                if (Test-Path $ApiErr) {
                    $tail = (Get-Content -Path $ApiErr -Tail 20 -ErrorAction SilentlyContinue) -join "`n"
                }
                throw "API did not become ready. See $ApiErr`n$tail"
            }
        }
    } while ($true)

    Write-Step "Starting Web on http://127.0.0.1:$WebPort ..."
    Start-Process -FilePath $WebPython `
        -ArgumentList @("-m", "http.server", "$WebPort", "--bind", "127.0.0.1") `
        -WorkingDirectory $WebDir `
        -RedirectStandardOutput $WebOut `
        -RedirectStandardError $WebErr `
        -WindowStyle Hidden

    try {
        Wait-PortListening -Port $WebPort -TimeoutSeconds 10
    } catch {
        $tail = ""
        if (Test-Path $WebErr) {
            $tail = (Get-Content -Path $WebErr -Tail 20 -ErrorAction SilentlyContinue) -join "`n"
        }
        throw "Web server did not become ready. See $WebErr`n$tail"
    }

    $Url = "http://127.0.0.1:$WebPort/?api=http://127.0.0.1:$ApiPort"
    Write-Host ""
    Write-Host "OpenInterview is ready." -ForegroundColor Green
    Write-Host "Open this URL:"
    Write-Host $Url -ForegroundColor Cyan
    Write-Host ""
    Write-Host "API log: $ApiOut"
    Write-Host "Web log: $WebOut"
    exit 0
} catch {
    Show-StartupFailure -Message $_.Exception.Message
    exit 1
}
