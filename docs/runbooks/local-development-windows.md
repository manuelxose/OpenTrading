# Runbook — Local Development on Windows (with a real MT4 terminal)

Companion to `docs/runbooks/local-development.md` (the canonical Linux/macOS
runbook — read it first; this page only covers what differs on Windows). Use
this page when you want to run the Core Platform **and** a real MetaTrader 4
terminal on the same Windows machine, which is the actual target topology
(§29, ADR-0016): Core runs on Linux, MT4 runs on Windows, they talk over a
private channel.

> **Read this before you start hunting for files:** `mt4/Experts/QuantBridgeEA.mq4`
> does not exist yet (Phase 6 shipped the wire protocol and a Python emulator
> only — see `mt4/README.md`). There is nothing to attach to an MT4 chart
> today. This runbook gets you to the same place the Linux runbook does — the
> full Core pipeline running against the emulator — plus a working MT4
> terminal installation ready for the day the EA lands. It does not invent
> steps for a file that isn't there yet.

## 1. Pick a topology

| Topology | What runs where | Recommended for |
|---|---|---|
| **A — WSL2 (recommended)** | Core Platform (Docker, Python, Postgres, …) inside a WSL2 Ubuntu distro; MT4 terminal native on Windows | Mirrors the real target architecture (Linux Core + Windows MT4) on one machine |
| **B — Native Windows** | Everything on Windows directly (uv-managed Python, Docker Desktop, `make` via Git Bash) | Only if WSL2 is unavailable (locked-down corporate machine, Windows Server without Hyper-V, …) |

Topology A is what the rest of this page assumes. Everything in
`docs/runbooks/local-development.md` (prerequisites, `make up`, endpoints,
verification, troubleshooting) applies **unchanged** inside the WSL2 shell —
it is Ubuntu, not Windows, from the Core Platform's point of view.

## 2. Set up WSL2 + Docker Desktop (once)

```powershell
# In an elevated PowerShell
wsl --install -d Ubuntu-24.04
# reboot if prompted, then finish the Ubuntu first-run (create a user)
```

- Install **Docker Desktop for Windows**, enable *"Use the WSL 2 based
  engine"* (Settings → General), then enable integration with your Ubuntu
  distro (Settings → Resources → WSL Integration → toggle `Ubuntu-24.04`).
- Prefer WSL2 **mirrored networking mode** (Windows 11 23H2+, WSL ≥ 2.0.9) so
  `127.0.0.1` is shared between Windows and the WSL2 VM — this is what makes
  §3's loopback story work without extra plumbing:

  ```ini
  # C:\Users\<you>\.wslconfig
  [wsl2]
  networkingMode=mirrored
  ```

  Then `wsl --shutdown` and reopen the Ubuntu shell. On older WSL2 (NAT mode)
  `127.0.0.1` on Windows does **not** reach services bound inside the VM by
  default; either upgrade (`wsl --update`) or use `netsh interface portproxy`
  to forward the specific ports you need (see §5 troubleshooting).

- **Clone the repo inside the Linux filesystem**, not under `/mnt/c/...`:

  ```bash
  # inside the Ubuntu WSL2 shell
  cd ~
  git clone <repo-url> OpenTrading
  cd OpenTrading
  ```

  `/mnt/c/...` works but is an order of magnitude slower for `git`/`uv`/
  Docker bind mounts, and Windows-side antivirus scanning of every file
  access makes `make test` painfully slow. Working from `~/OpenTrading`
  inside the WSL2 ext4 filesystem avoids both.

## 3. Install and run the Core Platform (inside WSL2)

From here, follow `docs/runbooks/local-development.md` verbatim, from
"First-time setup" onward:

```bash
uv sync --all-groups
make up
make health
```

Because Docker Desktop's WSL2 engine and mirrored networking share the
Windows host's `127.0.0.1`, you can open every endpoint from a normal Windows
browser without any extra configuration:

| Service | URL (from Windows) |
|---|---|
| API | `http://127.0.0.1:8000/healthz` |
| Grafana | `http://127.0.0.1:3001` |
| Langfuse | `http://127.0.0.1:3000` |
| MinIO console | `http://127.0.0.1:9001` |
| MLflow | `http://127.0.0.1:5000` |

Run the first PAPER cycle exactly as in `docs/GUIA_INSTALACION_USO.md` §5:

```bash
uv run python -m apps.worker run-once --llm mock
```

## 4. Install the MT4 terminal (Windows side)

1. Install your broker's MT4 terminal, or a demo terminal (e.g. the
   MetaQuotes demo server) purely to validate the installation. **No live
   account, ever, at this stage** — nothing in this repo is declared ready
   for real capital (`docs/PRODUCTION_READINESS.md`).
2. In the terminal: **File → Open Data Folder** — note the path
   (`%APPDATA%\MetaQuotes\Terminal\<hash>\`). This is where `MQL4\Experts\`
   and `MQL4\Include\` live.
3. **Tools → Options → Expert Advisors**:
   - ✅ "Allow automated trading"
   - ❌ leave "Allow WebRequest for listed URL" **empty/unchecked** — the
     protocol never uses `WebRequest` as a transport (ADR-0003, INV-5); if
     something asks you to enable it for this bridge, that's wrong.

### What you can actually do today

Because `QuantBridgeEA.mq4` isn't written yet, the terminal installed above
isn't wired to the Core Platform yet. What you *can* verify end-to-end today,
with the terminal installed and confirmed working (logged into a demo
account) but not yet connected:

```bash
# inside WSL2 — exercises the full Core↔"MT4" lifecycle against the Python
# emulator, on the same loopback ports the real EA will eventually use
uv run python -m adapters.mt4.cli smoke     # one-shot lifecycle check, exit 0 = OK
uv run python -m adapters.mt4.cli run       # persistent emulator (Ctrl-C to stop)
#   command: tcp://127.0.0.1:5555   events: tcp://127.0.0.1:5556   quotes: tcp://127.0.0.1:5557
```

This is the actual Phase 6 Definition of Done (`mt4/README.md`): the same
`order_intent_id` sent 100× never produces more than one trade — proven with
no MetaTrader installed. Installing the real terminal now just means you're
ready the moment the EA ships; it does not change what runs today.

### When `QuantBridgeEA.mq4` lands (future step — not yet possible)

For reference, once the EA exists the wiring will be: copy `mt4/Include/*`
into `<Data Folder>\MQL4\Include\`, the compiled EA into
`<Data Folder>\MQL4\Experts\`, install its MQL4 ZeroMQ binding, attach the EA
to a chart with AutoTrading on, and point `OT_MT4_COMMAND_ADDR` /
`OT_MT4_EVENTS_ADDR` / `OT_MT4_QUOTES_ADDR` at the terminal's endpoints
(loopback for same-box testing; WireGuard, never plain internet, for a
separate Windows host — INV-9). Do not treat this paragraph as a working
procedure — check `mt4/README.md` for the current status before following it.

## 5. Windows-specific troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Windows browser can't reach `127.0.0.1:<port>` bound inside WSL2 | You're on WSL2 NAT mode, not mirrored. Set `networkingMode=mirrored` in `.wslconfig` (§2) or `netsh interface portproxy add v4tov4 listenport=<port> listenaddress=127.0.0.1 connectport=<port> connectaddress=<wsl2-ip>` (get the IP with `wsl hostname -I`) |
| `git clone` / `uv sync` very slow, or file-watch loops | Repo is under `/mnt/c/...`; move it into the WSL2 filesystem (`~/OpenTrading`), see §2 |
| Shell scripts fail with `$'\r': command not found` | CRLF line endings from a Windows-side checkout; `git config --global core.autocrlf input` before cloning, or clone from inside WSL2 directly (avoids the problem entirely) |
| `make up` port conflicts (5432, 6379, 5000, …) | A native Windows service (e.g. a Windows-installed PostgreSQL, Skype, IIS) already owns the port; free it or change `OT_*_HOST_PORT` in `.env` |
| Docker Desktop reports a port as reserved despite nothing listening | Windows' dynamic port range reservation (Hyper-V); check with `netsh int ipv4 show excludedportrange protocol=tcp` and pick a free host port via `OT_*_HOST_PORT` |
| Timestamps/tests look skewed after the laptop slept | WSL2 clock drift after Windows sleep/resume; `wsl --shutdown` then reopen the shell resyncs the VM clock (matters for point-in-time correctness, INV-3) |
| `make` says "command not found" (Topology B, native Windows) | The Makefile is POSIX shell; run it from **Git Bash**, or run the underlying command directly — see the mapping below |
| MT4 terminal won't enable "Allow automated trading" | Some brokers disable it on demo accounts by policy; check the broker's terminal settings, this is unrelated to OpenTrading |

### Topology B (native Windows, no WSL2): `make` target → raw command

Only needed if you cannot use WSL2 at all. Docker Desktop still requires the
WSL2 or Hyper-V backend under the hood even in this topology.

| `make` target | Equivalent (PowerShell / cmd, from repo root) |
|---|---|
| `make setup` | `uv sync --all-groups` |
| `make up` | `docker compose --project-name opentrading-dev -f infra/compose/docker-compose.yml --env-file .env up -d --build --wait` then `docker compose ... run --rm minio-init` then `uv run alembic upgrade head` |
| `make down` | `docker compose --project-name opentrading-dev -f infra/compose/docker-compose.yml down --remove-orphans` |
| `make health` | `uv run python scripts/infra_health.py` |
| `make test` | `uv run pytest` |

## 6. Definition of Done (same as Linux, run from WSL2)

```bash
make up                 # 1. one command, everything healthy
make health             # 2. health checks green
make test-integration   # 3. integration smoke tests pass
uv run python -m adapters.mt4.cli smoke   # 4. MT4 lifecycle OK with no MetaTrader needed
```

Plus, on the Windows side: the MT4 terminal installed, logged into a demo
account, with automated trading enabled and `WebRequest` not used as a
transport.

## 7. See also

- `docs/runbooks/local-development.md` — canonical Linux/macOS runbook (read first)
- `docs/GUIA_INSTALACION_USO.md` — full install/usage guide (Spanish)
- `mt4/README.md` — MT4 layer status (protocol + emulator implemented; EA not started)
- `mt4/protocol/README.md` — normative wire protocol (ADR-0020)
- `docs/PRODUCTION_READINESS.md` — why this is not ready for real capital yet
