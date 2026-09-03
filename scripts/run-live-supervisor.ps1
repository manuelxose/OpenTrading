<#
.SYNOPSIS
    OpenTrading — run the LIVE_AUTO deterministic supervisor (single instance).

.DESCRIPTION
    Kills any stale live_supervisor process, then starts exactly one instance
    with the repository venv. The supervisor itself is fail-closed:
    startup reconciliation must be clean (INV-6) before any order can leave.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

# Single-instance guard: stale supervisors would fight over the REQ socket.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "apps\.live_supervisor" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Push-Location $RepoRoot
try {
    & $Python -m apps.live_supervisor run
}
finally {
    Pop-Location
}
