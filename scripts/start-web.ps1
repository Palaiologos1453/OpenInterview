$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$WebDir = Join-Path $Root "apps\web"

Set-Location $WebDir
python -m http.server 5173 --bind 127.0.0.1

