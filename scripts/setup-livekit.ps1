param([string]$Python = "", [switch]$SkipInstall)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
if (!$Python) { $Python = Join-Path $Root "voice_venv\Scripts\python.exe" }
if (!(Test-Path $Python)) { throw "Run setup-voice.ps1 first, or pass -Python with Python 3.10+." }
$AgentPython = Join-Path $Root "apps\livekit\.venv\Scripts\python.exe"
if (!(Test-Path $AgentPython)) {
    & $Python -m venv (Join-Path $Root "apps\livekit\.venv")
    if ($LASTEXITCODE) { throw "Failed to create isolated LiveKit environment." }
}
if (!$SkipInstall) {
    & $Python -m pip --python $AgentPython install -r (Join-Path $Root "apps\livekit\requirements.txt")
    if ($LASTEXITCODE) { throw "LiveKit dependency installation failed." }
}
& $AgentPython (Join-Path $Root "scripts\setup_livekit_assets.py")
if ($LASTEXITCODE) { throw "LiveKit asset setup failed." }
Write-Host "Installed. Start with .\scripts\start-livekit.ps1"
