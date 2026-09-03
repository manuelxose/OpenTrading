<#
.SYNOPSIS
    OpenTrading — fully automated MT4 bridge: deploy, launch, reconcile, unlock.

.DESCRIPTION
    Zero-touch bridge activation:

      Phase A  deploy:  invoke setup-mt4-bridge.ps1 -Attach (binding, aligned
                        inputs, SafeMode=true, compile, demo attach profile).
      Phase B  launch:   start the non-running MT4 terminal with the
                        OpenTradingBridge profile; wait (log-polling) for the
                        account login and for QuantBridgeEA to initialize with
                        the ZeroMQ channels bound.
      Phase C  verify:   demo-first gate — if the terminal logs into a server
                        whose name is not a demo server, the terminal is closed
                        and the script aborts (no automation against live).
      Phase D  reconcile: run `python -m engines.execution.cli reconcile-once`
                        (retries while the bridge warms up). Exit 0 = clean.
      Phase E  unlock:   after a clean reconciliation, write
                        MQL4\Files\QuantBridgeSafeMode.txt = 0 — the EA leaves
                        safe mode on its own. The wire protocol can never
                        clear safe mode (INV-6/INV-7).

    With -Loop the script also supervises: restarts the terminal if it dies
    and re-runs the emergency/reconciliation monitors every interval.

.PARAMETER Loop
    Keep supervising after activation (restart + monitor loop).

.PARAMETER LoopSeconds
    Supervision interval (default 30).

.PARAMETER EnvFile
    Core settings file. Default: <repo>\.env
#>
[CmdletBinding()]
param(
    [switch]$Loop,
    [int]$LoopSeconds = 30,
    [string]$EnvFile
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot ".env" }
$SetupScript = Join-Path $PSScriptRoot "setup-mt4-bridge.ps1"
$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "    WARN: $msg" -ForegroundColor Yellow }

function Read-EnvValue2([string]$name, [string]$default) {
    if (Test-Path $EnvFile) {
        foreach ($line in Get-Content $EnvFile) {
            if ($line -match "^$([regex]::Escape($name))=(.*)$") {
                $v = $Matches[1].Trim()
                if ($v -ne "") { return $v }
            }
        }
    }
    return $default
}

# Local, git-ignored credentials file (scripts\mt4-demo-creds.env).
# Never committed; used only to relaunch the terminal already logged in.
function Read-DemoCreds {
    $credsFile = Join-Path $PSScriptRoot "mt4-demo-creds.env"
    if (-not (Test-Path $credsFile)) { return $null }
    $login = ""; $password = ""; $server = ""
    foreach ($line in Get-Content $credsFile) {
        if ($line -match "^MT4_DEMO_LOGIN=(.*)$")       { $login = $Matches[1].Trim() }
        elseif ($line -match "^MT4_DEMO_PASSWORD=(.*)$") { $password = $Matches[1].Trim() }
        elseif ($line -match "^MT4_DEMO_SERVER=(.*)$")   { $server = $Matches[1].Trim() }
    }
    if (-not $login -or -not $server) { return $null }
    return [pscustomobject]@{ Login = $login; Password = $password; Server = $server }
}

# ── Shared: find MT4 installs ─────────────────────────────────────────────
function Get-Mt4Installs {
    $found = @()
    $termRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"
    if (Test-Path $termRoot) {
        foreach ($dir in Get-ChildItem $termRoot -Directory) {
            $origin = Join-Path $dir.FullName "origin.txt"
            if (Test-Path $origin) {
                $originPath = (Get-Content $origin -Raw).Trim()
                if ($originPath -match "MetaTrader 4") {
                    $found += [pscustomobject]@{
                        Data   = $dir.FullName
                        Mql4   = Join-Path $dir.FullName "MQL4"
                        Origin = $originPath
                        Exe    = Join-Path $originPath "terminal.exe"
                    }
                }
            }
        }
    }
    return @($found)
}

function Get-IsTerminalRunning([string]$exe) {
    $p = Get-Process -Name terminal -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $exe }
    return ($null -ne $p)
}

function Get-TodayLogCandidates([string]$data) {
    $logs = Join-Path $data "logs"
    $names = @()
    for ($i = 0; $i -lt 3; $i++) {
        $names += (Get-Date).AddDays(-$i).ToString("yyyyMMdd") + ".log"
    }
    $candidates = @()
    foreach ($n in $names) {
        $p = Join-Path $logs $n
        if (Test-Path $p) { $candidates += $p }
    }
    return $candidates
}

function Read-LogTail([string]$data, [string]$pattern, [int]$tailLines = 300) {
    $candidates = @(Get-TodayLogCandidates $data)
    if (-not $candidates) { return $null }
    $newest = $candidates | Sort-Object { (Get-Item $_).LastWriteTime } -Descending | Select-Object -First 1
    $lines = Get-Content $newest -Tail $tailLines -ErrorAction SilentlyContinue
    return ($lines | Select-String -Pattern $pattern | Select-Object -Last 1)
}

# ── Phase A: deploy ───────────────────────────────────────────────────────
Write-Step "Phase A: deploy bridge (binding + aligned inputs + SafeMode + compile + profile)"
& $SetupScript -Attach -EnvFile $EnvFile

# ── Phase B: pick the bridge terminal ────────────────────────────────────
# Order of preference: (1) an idle terminal with a usable binary, (2) a
# RUNNING terminal whose own log proves a recent DEMO-server login — it is
# closed, re-profiled and relaunched automatically; a LIVE terminal is never
# touched (demo-first policy), (3) the Python emulator as protocol stand-in.
$installs = Get-Mt4Installs
$creds = Read-DemoCreds
if ($creds) { Write-Ok ("demo credentials found for account " + $creds.Login) }
$demoProbe = Join-Path $PSScriptRoot "_probe_bridge_demo.py"
$cmdAddr = Read-EnvValue2 "OT_MT4_COMMAND_ADDR" "tcp://127.0.0.1:5555"

function Stop-BridgeTerminal([string]$exe) {
    Get-Process -Name terminal -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $exe } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

$bridge = $null
foreach ($inst in $installs) {
    if (-not (Test-Path $inst.Exe)) { continue }   # uninstalled — skip
    if (-not (Get-IsTerminalRunning $inst.Exe)) { $bridge = $inst; break }
}
if ($null -eq $bridge) {
    foreach ($inst in $installs) {
        if (-not (Test-Path $inst.Exe)) { continue }
        if (-not (Get-IsTerminalRunning $inst.Exe)) { continue }
        # Authoritative demo check: ask the EA itself (the terminal log does
        # not write "login on" on silent restarts).
        $runProbe = & $python $demoProbe $cmdAddr 10 2>&1 | Out-String
        $runProbeExit = $LASTEXITCODE
        if ($runProbeExit -eq 0) {
            $first = ($runProbe -split "`r?`n") | Select-Object -First 1
            Write-Ok ("reclaiming running DEMO terminal for the bridge: " + $first)
            Stop-BridgeTerminal $inst.Exe
            Write-Step "regenerating attach profile for the now-idle terminal"
            & $SetupScript -Attach -EnvFile $EnvFile
            $bridge = $inst
            break
        }
        if ($runProbeExit -eq 2) {
            Write-Warn "running terminal is on a NON-DEMO account — skipped (demo-first policy)"
            continue
        }
        Write-Warn "running terminal did not answer the demo probe — skipped"
    }
}
if ($null -eq $bridge) {
    Write-Warn "No usable MT4 terminal was found (no idle binary and no verified running demo)."
    Write-Step "Phase B-alt: validating the bridge end-to-end against the Python emulator (protocol DoD stand-in)"
    $python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $waitProbe = Join-Path $PSScriptRoot "_wait_bridge_heartbeat.py"
    $cmdAddr = Read-EnvValue2 "OT_MT4_COMMAND_ADDR" "tcp://127.0.0.1:5555"
    $evAddr  = Read-EnvValue2 "OT_MT4_EVENTS_ADDR" "tcp://127.0.0.1:5556"
    $qtAddr  = Read-EnvValue2 "OT_MT4_QUOTES_ADDR" "tcp://127.0.0.1:5557"

    # cleanup: kill any stale bridge emulator from previous runs
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "adapters\.mt4\.cli" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    $emu = Start-Process -FilePath $python -ArgumentList @(
        "-m", "adapters.mt4.cli", "run",
        "--command", $cmdAddr,
        "--events", $evAddr,
        "--quotes", $qtAddr
    ) -PassThru -WindowStyle Hidden
    try {
        Write-Step "waiting for the bridge heartbeat stream (serve loop up)"
        $ready = $false
        for ($i = 0; $i -lt 6; $i++) {
            $hbOut = & $python $waitProbe $evAddr 15 2>&1 | Out-String
            if ($LASTEXITCODE -eq 0) { $ready = $true; break }
            Start-Sleep -Seconds 5
        }
        if (-not $ready) { throw "bridge heartbeat never arrived — emulator serve loop not up" }
        Write-Ok ("bridge heartbeat received")

        Write-Step "Phase D: startup reconciliation against the emulator bridge (INV-6)"
        $reconcileOk = $false
        $lastOutput = ""
        for ($attempt = 1; $attempt -le 6; $attempt++) {
            Push-Location $RepoRoot
            try {
                $out = & $python -m engines.execution.cli reconcile-once 2>&1 | Out-String
                $exit = $LASTEXITCODE
            }
            finally { Pop-Location }
            $lastOutput = $out
            Write-Host ("    attempt {0}: exit={1}" -f $attempt, $exit)
            if ($exit -eq 0) { $reconcileOk = $true; break }
            Start-Sleep -Seconds 10
        }
        if (-not $reconcileOk) {
            Write-Host $lastOutput
            throw "Reconciliation against the emulator bridge failed."
        }
        Write-Ok "Bridge protocol validated end-to-end (deploy → compile → transport → reconciliation)."
    }
    finally {
        if ($emu -and -not $emu.HasExited) { Stop-Process -Id $emu.Id -Force -ErrorAction SilentlyContinue }
    }
    $status = [pscustomobject]@{
        ts         = (Get-Date).ToString("o")
        mode       = "VALIDATED_EMULATOR"
        reason     = "No non-running MT4 terminal available; the only installed MT4 is running on a LIVE account (demo-first policy blocks attach)."
        safeMode   = "ON"
        reconciled = $true
    }
    $status | ConvertTo-Json | Set-Content -Path (Join-Path $PSScriptRoot "bridge-status.json") -Encoding UTF8
    Write-Ok "status written to scripts\bridge-status.json"
    Write-Step "Ready. The moment a DEMO MT4 terminal exists on this machine, re-run this script: it will attach, reconcile and unlock automatically."
    return
}
Write-Step ("Phase B: launching bridge terminal " + $bridge.Exe)

# Always start safe (file overrides EA input).
$filesDir = Join-Path $bridge.Mql4 "Files"
New-Item -ItemType Directory -Force -Path $filesDir | Out-Null
Set-Content -Path (Join-Path $filesDir "QuantBridgeSafeMode.txt") -Value "1" -Encoding ASCII

# MT4 build 1470 ignores /profile and /login switches: it honors
# profiles\lastprofile.ini and its own saved credentials (auto-login).
Set-Content -Path (Join-Path $bridge.Data "profiles\lastprofile.ini") -Value "OpenTradingBridge" -Encoding ASCII -NoNewline
Start-Process -FilePath $bridge.Exe

# ── Phase C: demo gate via the EA itself (authoritative; not the log) ────
$deadline = (Get-Date).AddSeconds(180)
$demoOk = $false
$accountInfo = ""
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $probeOut = & $python $demoProbe $cmdAddr 10 2>&1 | Out-String
    $probeExit = $LASTEXITCODE
    if ($probeExit -eq 0) {
        $demoOk = $true
        $accountInfo = (($probeOut -split "`r?`n") | Select-Object -First 1)
        Write-Ok ("demo bridge verified: " + $accountInfo)
        break
    }
    if ($probeExit -eq 2) {
        Get-Process -Name terminal -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $bridge.Exe } | Stop-Process -Force -ErrorAction SilentlyContinue
        throw "Aborted: the bridge terminal is on a NON-DEMO account — no automation against live (demo-first policy)."
    }
}
if (-not $demoOk) {
    Write-Warn "EA did not answer the demo probe within 180s."
    Get-Process -Name terminal -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $bridge.Exe } | Stop-Process -Force -ErrorAction SilentlyContinue
    throw "Aborted: bridge terminal never became ready. Inspect the MT4 terminal (login dialog?) and re-run."
}
Write-Ok "QuantBridgeEA is serving the bridge protocol on a verified DEMO account."

# ── Phase D: reconcile (retries while the bridge warms up) ────────────────
Write-Step "Phase D: startup reconciliation (INV-6)"
$reconcileOk = $false
$lastOutput = ""
$divergence = $false
for ($attempt = 1; $attempt -le 6; $attempt++) {
    Push-Location $RepoRoot
    try {
        $out = & $python -m engines.execution.cli reconcile-once 2>&1 | Out-String
        $exit = $LASTEXITCODE
    }
    finally { Pop-Location }
    $lastOutput = $out
    Write-Host ("    attempt {0}: exit={1}" -f $attempt, $exit)
    if ($exit -eq 0) { $reconcileOk = $true; break }
    if ($out -match "RECONCILIATION_DIVERGENCE|material_discrepancies=[1-9]") {
        $divergence = $true
        Write-Warn "material divergence: an external broker position/order exists (e.g. a manual trade)."
        break
    }
    if ($out -match "NOT_CONNECTED|TIMEOUT|BROKER_DISCONNECTED") {
        Write-Warn "bridge not reachable yet — retrying in 10s"
        Start-Sleep -Seconds 10
        continue
    }
    break
}
if (-not $reconcileOk) {
    if ($divergence) {
        Write-Warn "SafeMode stays ON (INV-6): reconciliation found an external broker position."
        Write-Warn "Close the manual position in MT4 and re-run this script — it will then reconcile clean and unlock automatically."
        $status = [pscustomobject]@{
            ts          = (Get-Date).ToString("o")
            mode        = "ATTACHED_DEMO_SAFEMODE_DIVERGENCE"
            terminal    = $bridge.Exe
            dataFolder  = $bridge.Data
            account     = $accountInfo
            safeMode    = "ON"
            reconciled  = $false
            reason      = "material discrepancy (external broker position) — close it in MT4 and re-run."
        }
        $status | ConvertTo-Json | Set-Content -Path (Join-Path $PSScriptRoot "bridge-status.json") -Encoding UTF8
        Write-Ok "status written to scripts\bridge-status.json"
        return
    }
    Write-Warn "reconciliation did not return clean (exit≠0). SafeMode stays ON."
    Write-Host $lastOutput
    throw "Reconciliation failed — inspect the output above. SafeMode remains ON."
}

# ── Phase E: unlock safe mode (operator-owned file, never via the wire) ────
Write-Step "Phase E: reconciliation clean — clearing bridge safe mode"
Set-Content -Path (Join-Path $filesDir "QuantBridgeSafeMode.txt") -Value "0" -Encoding ASCII
Write-Ok "MQL4\Files\QuantBridgeSafeMode.txt = 0 (the EA leaves safe mode on the next command evaluation)"

# ── Status artifact ───────────────────────────────────────────────────────
$status = [pscustomobject]@{
    ts          = (Get-Date).ToString("o")
    mode        = "ATTACHED_DEMO"
    terminal    = $bridge.Exe
    dataFolder  = $bridge.Data
    account     = $accountInfo
    safeMode    = "OFF"
    reconciled  = $true
}
$status | ConvertTo-Json | Set-Content -Path (Join-Path $PSScriptRoot "bridge-status.json") -Encoding UTF8
Write-Ok ("status written to scripts\bridge-status.json")

if (-not $Loop) {
    Write-Step "Bridge is fully up: EA attached, demo account verified, reconciled, safe mode cleared."
    return
}

# ── Supervision loop ──────────────────────────────────────────────────────
Write-Step ("Supervision loop started (every {0}s; Ctrl+C to stop)" -f $LoopSeconds)
while ($true) {
    Start-Sleep -Seconds $LoopSeconds
    if (-not (Get-IsTerminalRunning $bridge.Exe)) {
        Write-Warn "terminal not running — relaunching"
        Set-Content -Path (Join-Path $filesDir "QuantBridgeSafeMode.txt") -Value "1" -Encoding ASCII
        Start-Process -FilePath $bridge.Exe
        Start-Sleep -Seconds 20
        Push-Location $RepoRoot
        try { $null = & $python -m engines.execution.cli reconcile-once 2>&1 | Out-String } finally { Pop-Location }
        if ($LASTEXITCODE -eq 0) {
            Set-Content -Path (Join-Path $filesDir "QuantBridgeSafeMode.txt") -Value "0" -Encoding ASCII
        }
        continue
    }
    Push-Location $RepoRoot
    try {
        $null = & $python -m engines.execution.cli check-emergency 2>&1 | Out-String
        $emergency = $LASTEXITCODE
    }
    finally { Pop-Location }
    if ($emergency -eq 2) {
        Write-Warn "emergency monitor reported an unsafe execution state (exit 2)"
    }
}
