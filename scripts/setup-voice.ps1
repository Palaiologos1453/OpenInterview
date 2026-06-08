param(
    [string]$Python = "python",
    [switch]$SkipInstall,
    [switch]$DownloadModels,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ApiDir = Join-Path $Root "apps\api"
$VoiceVenv = Join-Path $Root "voice_venv"
$VoicePython = Join-Path $VoiceVenv "Scripts\python.exe"
$Requirements = Join-Path $ApiDir "requirements-voice.txt"

function Write-Step {
    param([string]$Message)
    Write-Host "[OpenInterview Voice] $Message"
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
        throw "Python $versionText is too old. Voice runtime requires Python 3.10+."
    }
    return $versionText.Trim()
}

function Invoke-DownloadIfMissing {
    param(
        [string]$Repo,
        [string]$LocalDir,
        [string]$Probe
    )
    $target = Join-Path $Root $LocalDir
    $probePath = Join-Path $Root $Probe
    if (Test-Path $probePath) {
        Write-Step "Model already exists: $LocalDir"
        return
    }
    Write-Step "Downloading $Repo -> $LocalDir"
    & $VoicePython -c "from huggingface_hub import snapshot_download; import sys; snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2], local_dir_use_symlinks=False)" $Repo $target
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download $Repo. You can download it manually into $LocalDir."
    }
}

function Copy-SileroVadIfMissing {
    $target = Join-Path $Root "models\vad\silero-vad\silero_vad.onnx"
    if (Test-Path $target) {
        Write-Step "VAD model already exists: models\vad\silero-vad\silero_vad.onnx"
        return
    }
    Write-Step "Copying Silero VAD ONNX from the silero-vad package..."
    $source = & $VoicePython -c "import inspect, pathlib, silero_vad; root=pathlib.Path(inspect.getfile(silero_vad)).parent; print(root / 'data' / 'silero_vad.onnx')"
    if ($LASTEXITCODE -ne 0 -or -not $source -or -not (Test-Path $source.Trim())) {
        throw "silero-vad package is installed, but silero_vad.onnx was not found."
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -Force -Path $source.Trim() -Destination $target
}

Write-Step "Workspace: $Root"

if (-not (Test-Path $VoicePython)) {
    Write-Step "Creating voice_venv..."
    & $Python -m venv $VoiceVenv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create voice_venv. Pass -Python with a valid Python 3.10+ executable."
    }
}

$version = Test-PythonVersion -PythonPath $VoicePython
Write-Step "Using Python $version at $VoicePython"

if (-not $SkipInstall) {
    Write-Step "Installing API package and voice dependencies..."
    & $VoicePython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }
    & $VoicePython -m pip install -e $ApiDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to install API package." }
    & $VoicePython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw "Failed to install voice requirements." }
    & $VoicePython -m pip install huggingface_hub
    if ($LASTEXITCODE -ne 0) { throw "Failed to install huggingface_hub." }
}

if ($DownloadModels) {
    Copy-SileroVadIfMissing

    Invoke-DownloadIfMissing `
        -Repo "FunAudioLLM/SenseVoiceSmall" `
        -LocalDir "models\asr\SenseVoiceSmall" `
        -Probe "models\asr\SenseVoiceSmall\model.pt"

    Invoke-DownloadIfMissing `
        -Repo "FunAudioLLM/Fun-CosyVoice3-0.5B-2512" `
        -LocalDir "models\tts\Fun-CosyVoice3-0.5B" `
        -Probe "models\tts\Fun-CosyVoice3-0.5B\llm.pt"
}

if (Test-Path "D:\CosyVoice") {
    $env:OPENINTERVIEW_COSYVOICE_PATH = "D:\CosyVoice"
    $env:PYTHONPATH = "D:\CosyVoice;$ApiDir;$env:PYTHONPATH"
    Write-Step "Detected CosyVoice runtime: D:\CosyVoice"
} else {
    $env:PYTHONPATH = "$ApiDir;$env:PYTHONPATH"
    Write-Step "CosyVoice runtime not found at D:\CosyVoice. Local TTS will fail until CosyVoice runtime is installed or OPENINTERVIEW_COSYVOICE_PATH is set."
}

$ffmpeg = Get-ChildItem (Join-Path $Root "tools\ffmpeg") -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ffmpeg) {
    $env:PATH = "$($ffmpeg.Directory.FullName);$env:PATH"
    Write-Step "Detected portable ffmpeg: $($ffmpeg.FullName)"
}

if (-not $SkipSmoke) {
    Write-Step "Running local voice readiness check..."
    & $VoicePython -c "from openinterview_api.services.readiness import readiness_report; import json; print(json.dumps(readiness_report(), ensure_ascii=False, indent=2))"
    if ($LASTEXITCODE -ne 0) { throw "Readiness check failed." }
    Write-Step "For full ASR/TTS smoke test, start the app and click '语音自检', or run: .\voice_venv\Scripts\python.exe -c `"from openinterview_api.services.readiness import readiness_smoke_report; import json; print(json.dumps(readiness_smoke_report(include_voice=True), ensure_ascii=False, indent=2))`""
}

Write-Host ""
Write-Host "Voice setup finished." -ForegroundColor Green
Write-Host "Start app with: .\scripts\start-local.ps1"
