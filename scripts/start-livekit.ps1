param([int]$ApiPort = 8010, [int]$WebPort = 5180, [string]$DatabasePath = "")
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$AgentPython = Join-Path $Root "apps\livekit\.venv\Scripts\python.exe"
$VoicePython = Join-Path $Root "voice_venv\Scripts\python.exe"
$Server = Join-Path $Root "tools\livekit\1.13.7\livekit-server.exe"
$ConfigPath = Join-Path $Root "configs\livekit.local.json"
$LogDir = Join-Path $Root "logs\livekit"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Manifest = Join-Path $LogDir "processes.json"
if (Test-Path $Manifest) { throw "Run scripts/stop-livekit.ps1 before starting another stack." }
foreach ($File in @($AgentPython, $VoicePython, $Server, $ConfigPath)) {
    if (!(Test-Path $File)) { throw "Missing $File. Run scripts/setup-livekit.ps1 first." }
}
foreach ($Port in @(7880, 7881, $ApiPort, $WebPort)) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $Port is occupied. Stop the old local stack or select other API/Web ports."
    }
}
$Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$Config.api_url = "http://127.0.0.1:$ApiPort"
$Config | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding utf8
$Processes = @()
function Start-LocalProcess($Executable, $Arguments, $Name) {
    $Process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $LogDir "$Name.out.log") -RedirectStandardError (Join-Path $LogDir "$Name.err.log")
    $script:Processes += @{ id = $Process.Id; started = $Process.StartTime.ToUniversalTime().ToString("o"); name = $Name }
    ConvertTo-Json -InputObject @($script:Processes) | Set-Content -LiteralPath $Manifest -Encoding utf8
}
function Wait-Http($Url) {
    $Deadline = (Get-Date).AddSeconds(45)
    do {
        try { $null = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2; return } catch { Start-Sleep -Milliseconds 300 }
    } while ((Get-Date) -lt $Deadline)
    throw "Service failed to start: $Url. See $LogDir."
}
try {
    $env:PYTHONPATH = Join-Path $Root "apps\api"
    $env:PYTHONIOENCODING = "utf-8"
    $env:HF_HUB_OFFLINE = "1"
    $env:OTEL_SDK_DISABLED = "true"
    if ($DatabasePath) { $env:OPENINTERVIEW_DB_PATH = $DatabasePath }
    Start-LocalProcess $VoicePython @('-m','uvicorn','openinterview_api.main:app','--host','127.0.0.1','--port',"$ApiPort") 'api'
    Wait-Http "http://127.0.0.1:$ApiPort/health"
    Start-LocalProcess $Server @('--config','configs/livekit.local.yaml','--bind','127.0.0.1','--node-ip','127.0.0.1') 'server'
    Wait-Http 'http://127.0.0.1:7880'
    Start-LocalProcess $AgentPython @('apps/livekit/worker.py','start') 'agent'
    $AgentDeadline = (Get-Date).AddSeconds(30)
    do {
        if (Select-String -LiteralPath (Join-Path $LogDir 'agent.out.log') -Pattern 'registered worker' -Quiet -ErrorAction SilentlyContinue) { break }
        if ((Get-Date) -gt $AgentDeadline) { throw "Agent did not register. See $LogDir." }
        Start-Sleep -Milliseconds 300
    } while ($true)
    Start-LocalProcess $AgentPython @('-m','uvicorn','controller:app','--app-dir','apps/livekit','--host','127.0.0.1','--port',"$WebPort") 'web'
    Wait-Http "http://127.0.0.1:$WebPort/health"
    Write-Host "Local voice interview: http://127.0.0.1:$WebPort"
    Write-Host "Logs: $LogDir"
    Write-Host 'Stop with .\scripts\stop-livekit.ps1'
} catch {
    & (Join-Path $PSScriptRoot 'stop-livekit.ps1')
    throw
}
