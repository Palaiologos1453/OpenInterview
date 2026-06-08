$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ApiDir = Join-Path $Root "apps\api"
$VoicePython = Join-Path $Root "voice_venv\Scripts\python.exe"

$env:OPENINTERVIEW_ENV = "production"
$env:OPENINTERVIEW_REQUIRE_AUTH = "true"
$env:OPENINTERVIEW_CORS_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173"
if (Test-Path "D:\CosyVoice") {
    $env:OPENINTERVIEW_COSYVOICE_PATH = "D:\CosyVoice"
    $env:PYTHONPATH = "D:\CosyVoice;$env:PYTHONPATH"
}
$ffmpeg = Get-ChildItem (Join-Path $Root "tools\ffmpeg") -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ffmpeg) {
    $env:PATH = "$($ffmpeg.Directory.FullName);$env:PATH"
}

Set-Location $ApiDir
if (Test-Path $VoicePython) {
    $env:PYTHONPATH = "$ApiDir;$env:PYTHONPATH"
    & $VoicePython -m uvicorn openinterview_api.main:app --host 127.0.0.1 --port 8001
} else {
    python -m uvicorn openinterview_api.main:app --host 127.0.0.1 --port 8001
}
