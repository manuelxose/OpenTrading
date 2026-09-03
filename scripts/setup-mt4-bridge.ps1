<#
.SYNOPSIS
    OpenTrading — automated MT4 bridge setup (ADR-0020 / QuantBridgeEA).

.DESCRIPTION
    Fully automates bridge activation on this machine:

      1. Installs the mql-zmq binding (dingmaotu/mql-zmq v1.5, Apache-2.0):
         Include/Zmq + Include/Mql (mql4-lib subset) + 32-bit Library/MT4 DLLs.
      2. Enables QUANT_BRIDGE_ZMQ in the deployed transport include.
      3. Aligns the EA inputs with the Core settings read from .env:
         InputCommandAddr / InputEventsAddr / InputQuotesAddr from
         OT_MT4_COMMAND_ADDR / OT_MT4_EVENTS_ADDR / OT_MT4_QUOTES_ADDR, and
         InputSymbolWhitelist from OT_PAPER_INSTRUMENTS.
      4. Starts in safe mode: InputSafeMode=true until the first
         reconciliation passes (INV-6).
      5. Copies everything into every detected MT4 data folder, compiles with
         the terminal's own MetaEditor and verifies "0 errors".

    Safety: the script NEVER touches a running terminal's process and never
    auto-attaches to a running (possibly live) account. With -Attach it writes
    a chart profile (best-effort) so the EA can be attached on a DEMO terminal
    in one step; verify the attachment in the terminal afterwards.

.PARAMETER Attach
    Also generate the OpenTradingBridge chart profile for terminals that are
    NOT currently running (demo-first policy).

.PARAMETER DataFolders
    Optional list of specific MT4 data folders. Default: auto-detect from
    %APPDATA%\MetaQuotes\Terminal\*\origin.txt.

.PARAMETER EnvFile
    Core settings file to read. Default: <repo>\.env

.PARAMETER MqlZmqUrl
    Binding archive. Default: master tarball of dingmaotu/mql-zmq.

.EXAMPLE
    .\scripts\setup-mt4-bridge.ps1              # install + configure + compile
    .\scripts\setup-mt4-bridge.ps1 -Attach      # also prepare demo attach profile
#>
[CmdletBinding()]
param(
    [switch]$Attach,
    [string[]]$DataFolders,
    [string]$EnvFile,
    [string]$MqlZmqUrl = "https://github.com/dingmaotu/mql-zmq/archive/refs/heads/master.zip"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot ".env" }

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "    WARN: $msg" -ForegroundColor Yellow }

# ── 0. Read Core settings from .env ───────────────────────────────────────
function Read-EnvValue([string]$name, [string]$default) {
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

$CommandAddr = Read-EnvValue "OT_MT4_COMMAND_ADDR" "tcp://127.0.0.1:5555"
$EventsAddr  = Read-EnvValue "OT_MT4_EVENTS_ADDR"  "tcp://127.0.0.1:5556"
$QuotesAddr  = Read-EnvValue "OT_MT4_QUOTES_ADDR"  "tcp://127.0.0.1:5557"
$Instruments = Read-EnvValue "OT_PAPER_INSTRUMENTS" "EURUSD"
Write-Step "Core settings: command=$CommandAddr events=$EventsAddr quotes=$QuotesAddr whitelist=$Instruments"

# ── 1. Detect MT4 installations ──────────────────────────────────────────
function Find-Mt4Installs {
    $found = @()
    $termRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"
    if (Test-Path $termRoot) {
        foreach ($dir in Get-ChildItem $termRoot -Directory) {
            $origin = Join-Path $dir.FullName "origin.txt"
            if (Test-Path $origin) {
                $originPath = (Get-Content $origin -Raw).Trim()
                if ($originPath -match "MetaTrader 4") {
                    $mql4 = Join-Path $dir.FullName "MQL4"
                    if (Test-Path $mql4) {
                        $found += [pscustomobject]@{
                            Data    = $dir.FullName
                            Mql4    = $mql4
                            Origin  = $originPath
                        }
                    }
                }
            }
        }
    }
    return $found
}

$installs = @()
if ($DataFolders) {
    foreach ($d in $DataFolders) {
        if (Test-Path (Join-Path $d "MQL4")) {
            $installs += [pscustomobject]@{ Data = $d; Mql4 = (Join-Path $d "MQL4"); Origin = "" }
        } else { Write-Warn "no MQL4 folder at $d" }
    }
}
if (-not $installs) { $installs = @(Find-Mt4Installs) }
if (-not $installs) { throw "No MetaTrader 4 installations found." }
Write-Step ("MT4 data folders: " + (($installs | ForEach-Object { $_.Data }) -join " ; "))

# ── 2. Download + install mql-zmq binding ────────────────────────────────
$tmp = Join-Path $env:TEMP ("mql-zmq-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $tmp | Out-Null
$zip = Join-Path $tmp "mql-zmq.zip"
Write-Step "Downloading mql-zmq binding..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $MqlZmqUrl -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $tmp
$bindingRoot = Get-ChildItem $tmp -Directory | Select-Object -First 1
$zmqInc  = Join-Path $bindingRoot.FullName "Include\Zmq"
$mqlInc  = Join-Path $bindingRoot.FullName "Include\Mql"
$dllDir  = Join-Path $bindingRoot.FullName "Library\MT4"
if (-not (Test-Path $zmqInc)) { throw "binding archive lacks Include\Zmq" }
if (-not (Test-Path $mqlInc)) { throw "binding archive lacks Include\Mql (mql4-lib subset)" }
if (-not (Test-Path $dllDir))  { throw "binding archive lacks Library\MT4 DLLs" }
Write-Ok ("binding extracted: " + $bindingRoot.Name)

$repoInclude = Join-Path $RepoRoot "mt4\Include"
$repoExperts = Join-Path $RepoRoot "mt4\Experts"
if (-not (Test-Path (Join-Path $repoInclude "QuantBridgeProtocol.mqh"))) {
    throw "repo include missing: $repoInclude\QuantBridgeProtocol.mqh"
}

# ── 3. Deploy + configure + compile per MT4 install ──────────────────────
function Patch-EaSource([string]$src, [string]$cmd, [string]$ev, [string]$qt, [string]$wl) {
    $c = Get-Content $src -Raw
    $c = [regex]::Replace($c, '(InputCommandAddr\s*=\s*")[^"]*(")', '${1}' + $cmd + '${2}')
    $c = [regex]::Replace($c, '(InputEventsAddr\s*=\s*")[^"]*(")',  '${1}' + $ev + '${2}')
    $c = [regex]::Replace($c, '(InputQuotesAddr\s*=\s*")[^"]*(")',  '${1}' + $qt + '${2}')
    $c = [regex]::Replace($c, '(InputSafeMode\s*=\s*)false;', '${1}true;')
    $c = [regex]::Replace($c, '(InputSymbolWhitelist\s*=\s*")[^"]*(")', '${1}' + $wl + '${2}')
    return $c
}

function Enable-ZmqDefine([string]$src) {
    $c = Get-Content $src -Raw
    return $c.Replace("//#define QUANT_BRIDGE_ZMQ", "#define QUANT_BRIDGE_ZMQ")
}

foreach ($inst in $installs) {
    Write-Step ("Deploying to " + $inst.Data)

    # 3a. binding includes + DLLs
    $incDir = Join-Path $inst.Mql4 "Include"
    $libDir = Join-Path $inst.Mql4 "Libraries"
    New-Item -ItemType Directory -Force -Path (Join-Path $incDir "Zmq") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $incDir "Mql") | Out-Null
    New-Item -ItemType Directory -Force -Path $libDir | Out-Null
    Copy-Item (Join-Path $zmqInc "*") -Destination (Join-Path $incDir "Zmq") -Recurse -Force
    Copy-Item (Join-Path $mqlInc "*") -Destination (Join-Path $incDir "Mql") -Recurse -Force
    # DLLs may be locked while a terminal with the EA attached is running;
    # a previously deployed identical copy is already in place.
    Copy-Item (Join-Path $dllDir "*.dll") -Destination $libDir -Force -ErrorAction SilentlyContinue
    $dlls = Get-ChildItem $libDir -Filter "*.dll" | Where-Object { $_.Name -match "zmq|sodium" }
    Write-Ok ("binding installed: " + (($dlls | ForEach-Object { $_.Name }) -join ", "))

    # 3b. bridge includes (transport enabled for the real sockets)
    Copy-Item (Join-Path $repoInclude "QuantBridgeProtocol.mqh") (Join-Path $incDir "QuantBridgeProtocol.mqh") -Force
    $zmqDeployed = Join-Path $incDir "QuantBridgeZmq.mqh"
    $enabled = Enable-ZmqDefine (Join-Path $repoInclude "QuantBridgeZmq.mqh")
    Set-Content -Path $zmqDeployed -Value $enabled -Encoding UTF8 -NoNewline
    Write-Ok "QUANT_BRIDGE_ZMQ enabled in deployed transport include"

    # 3c. EA with Core-aligned inputs + SafeMode=true
    $eaDir = Join-Path $inst.Mql4 "Experts"
    New-Item -ItemType Directory -Force -Path $eaDir | Out-Null
    $eaDeployed = Join-Path $eaDir "QuantBridgeEA.mq4"
    $patched = Patch-EaSource (Join-Path $repoExperts "QuantBridgeEA.mq4") `
                               $CommandAddr $EventsAddr $QuotesAddr $Instruments
    Set-Content -Path $eaDeployed -Value $patched -Encoding UTF8 -NoNewline
    Write-Ok "EA deployed with SafeMode=true and Core-aligned endpoints"

    # 3d. compile with a MetaEditor from any installed MT4 (all MT4 builds share the compiler)
    $metaEditor = ""
    if ($inst.Origin -and (Test-Path (Join-Path $inst.Origin "metaeditor.exe"))) {
        $metaEditor = Join-Path $inst.Origin "metaeditor.exe"
    } else {
        $metaEditor = Get-ChildItem "C:\Program Files (x86)" -Filter "metaeditor.exe" -Recurse -Depth 2 -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "MetaTrader 4" } | Select-Object -First 1 -ExpandProperty FullName
    }
    if ($metaEditor -and (Test-Path $metaEditor)) {
        $log = Join-Path $env:TEMP "quantbridge_compile_$([guid]::NewGuid().ToString('N').Substring(0,8)).log"
        $p = Start-Process -FilePath $metaEditor -ArgumentList "/compile:`"$eaDeployed`"", "/log:`"$log`"" -PassThru -Wait
        if (Test-Path $log) {
            $summary = Get-Content $log | Where-Object { $_ -match "Result:" } | Select-Object -Last 1
            $errCount = @(Get-Content $log | Where-Object { $_ -match " error \d+" }).Count
            Write-Host "    compile log: $summary"
            if ($errCount -eq 0) {
                $ex4 = Join-Path $eaDir "QuantBridgeEA.ex4"
                if (Test-Path $ex4) {
                    Write-Ok ("compiled: " + $ex4 + " (" + (Get-Item $ex4).Length + " bytes)")
                } else { Write-Warn "no .ex4 produced" }
            } else {
                Write-Warn "compilation reported errors — see $log"
            }
        } else { Write-Warn "metaeditor produced no log" }
    } else {
        Write-Warn "metaeditor.exe not found for $($inst.Data) — skipped compile"
    }
}

# ── 4. Optional: demo attach profile (never for a running terminal) ──────
function New-BridgeProfile($inst, [string]$cmd, [string]$ev, [string]$qt, [string]$wl) {
    $terminal = Join-Path $inst.Origin "terminal.exe"
    if (-not $inst.Origin) {
        Write-Warn "origin unknown for $($inst.Data) — cannot create profile"
        return
    }
    $running = Get-Process -Name terminal -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $terminal }
    if ($running) {
        $title = $running[0].MainWindowTitle
        if ($title -match "Live") {
            Write-Warn "REFUSED attach: $terminal is RUNNING on a LIVE account ($title). Validate on demo first."
            return
        }
        Write-Warn "REFUSED attach: $terminal is currently running. Close it first (demo-first policy)."
        return
    }
    $profileDir = Join-Path $inst.Data "profiles\OpenTradingBridge"
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
    $symbol = ($wl -split ",")[0]
    if (-not $symbol) { $symbol = "EURUSD" }
    # Real MT4 .chr format (verified against a terminal-written chart file):
    # the expert lives in an <expert> block with <inputs> before </chart>.
    $chr = @"
<chart>
symbol=$symbol
period=60
digits=5
scale=4
graph=1
fore=1
grid=1
volume=0
scroll=0
shift=1
ohlc=1
one_click=1
askline=0
days=1
descriptions=0
shift_size=20
fixed_pos=0
window_left=0
window_top=0
window_right=196
window_bottom=311
window_type=1
background_color=0
foreground_color=16777215
barup_color=65280
bardown_color=65280
bullcandle_color=0
bearcandle_color=16777215
chartline_color=65280
volumes_color=3329330
grid_color=10061943
askline_color=255
stops_color=255
<expert>
name=QuantBridgeEA
flags=855
window_num=0
<inputs>
InputCommandAddr=$cmd
InputEventsAddr=$ev
InputQuotesAddr=$qt
InputSafeMode=true
InputVerifyChecksums=true
InputSymbolWhitelist=$wl
InputMaxSpreadPoints=30.0
InputMaxQuoteAgeSeconds=5
InputHeartbeatSeconds=1.0
InputPollMilliseconds=100
InputBridgeId=mt4-bridge-1
</inputs>
</expert>
</chart>
"@
    Set-Content -Path (Join-Path $profileDir "chart01.CHR") -Value $chr -Encoding ASCII
    Write-Ok ("attach profile ready: " + $profileDir)
}

if ($Attach) {
    foreach ($inst in $installs) {
        Write-Step ("Attach profile for " + $inst.Data)
        New-BridgeProfile $inst $CommandAddr $EventsAddr $QuotesAddr $Instruments
    }
}

Write-Step "Bridge setup complete."
Write-Host ""
Write-Host "Next steps (manual, safety-gated):"
Write-Host "  1. Start the DEMO terminal, load profile 'OpenTradingBridge', confirm QuantBridgeEA is attached (smiley face)."
Write-Host "  2. On the Core side, run a reconciliation first (SafeMode stays ON until it passes):"
Write-Host "       python -m engines.execution.cli reconcile-once"
Write-Host "  3. Only after demo validation, flip InputSafeMode=false on the real bridge."
Write-Host ""
Write-Host "  (Bridge self-test without MT4: python -m adapters.mt4.cli run --command $CommandAddr --events $EventsAddr --quotes $QuotesAddr)"
Write-Host "  (Protocol DoD suite:           python -m pytest tests/unit/mt4)"
