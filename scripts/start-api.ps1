$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ApiDir = Join-Path $Root "apps\api"
$VoicePython = Join-Path $Root "voice_venv\Scripts\python.exe"

Set-Location $ApiDir

if (Test-Path $VoicePython) {
    $env:PYTHONPATH = "$ApiDir;$env:PYTHONPATH"
    if (Test-Path "D:\CosyVoice") {
        $env:OPENINTERVIEW_COSYVOICE_PATH = "D:\CosyVoice"
        $env:PYTHONPATH = "D:\CosyVoice;$env:PYTHONPATH"
    }
    $ffmpeg = Get-ChildItem (Join-Path $Root "tools\ffmpeg") -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ffmpeg) {
        $env:PATH = "$($ffmpeg.Directory.FullName);$env:PATH"
    }
    & $VoicePython -m uvicorn openinterview_api.main:app --host 127.0.0.1 --port 8000 --reload
} else {
    if (-not (Test-Path ".venv")) {
        python -m venv .venv
    }

    & ".\.venv\Scripts\python.exe" -m pip install -e .
    & ".\.venv\Scripts\python.exe" -m uvicorn openinterview_api.main:app --host 127.0.0.1 --port 8000 --reload
}
