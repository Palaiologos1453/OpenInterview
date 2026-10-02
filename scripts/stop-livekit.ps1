$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$Manifest = Join-Path $Root 'logs\livekit\processes.json'
if (!(Test-Path $Manifest)) { Write-Host 'No managed LiveKit processes.'; return }
$Entries = @(Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json)
[array]::Reverse($Entries)
foreach ($Entry in $Entries) {
    $Process = Get-Process -Id $Entry.id -ErrorAction SilentlyContinue
    if ($Process -and $Process.StartTime.ToUniversalTime().Ticks -eq ([datetime]$Entry.started).ToUniversalTime().Ticks) {
        # Kill only the process tree recorded by our launcher, never by name.
        & taskkill.exe /PID $Entry.id /T /F | Out-Null
    }
}
Remove-Item -LiteralPath $Manifest
Write-Host 'Stopped managed LiveKit processes.'
