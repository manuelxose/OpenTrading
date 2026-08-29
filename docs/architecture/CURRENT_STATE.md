# Current State — OpenTrading Repository

- **Audit date:** 2026-08-26
- **Auditor role:** Principal Architect
- **Repository:** `/var/www/OpenTrading`
- **Canonical target source:** `docs/architecture.md` v1.0 (2026-08-26, Spanish, 2468 lines)
- **Method:** complete file inventory (every non-git file listed), git inspection, Graphify
  re-index run, and full read of all documentation and governance files.

---

## 1. Snapshot facts (repository evidence)

| Fact | Evidence |
|---|---|
| Git history | Single commit `01462f8` — "PRE-00: repository-specific AI engineering team foundation" |
| Branch / remote | `main`, no remotes configured |
| Working tree | Clean at audit start (this task adds `docs/architecture/` + `docs/ADR/`) |
| Code files | **0** (no `.py`, `.ts`, `.js`, `.mq4`, `.sql`, `.yaml`, `.toml` anywhere) |
| Graphify index | Ran `graphify extract . --code-only` → "found 0 code, 69 docs" → **empty graph (0 nodes)**, as documented in `graphify-out/README.md` |
| Trading functionality | **None** — prohibited during PRE-00 by every adapter (`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-canonical.mdc`, `.github/copilot-instructions.md`) |
| Secrets in repo | **None**. `.gitignore` excludes `.env`, `.env.*`, `secrets/`, `*.key`, `*.pem` |

## 2. Complete repository inventory

```text
OpenTrading/
├── .ai/                      # canonical AI engineering layer (52 files)
│   ├── README.md
│   ├── agents/               # 12 specialist agent cards
│   ├── skills/               # 35 procedural skills (8 categories)
│   ├── rules/                # architecture-invariants, definition-of-done,
│   │                         #   cross-review-rules, context-usage
│   ├── workflows/            # task-routing, adr-workflow, verification-workflow
│   ├── context/              # repo-map, domain-glossary
│   └── templates/            # adr, agent-output, review-report
├── .cursor/rules/00-canonical.mdc   # Cursor adapter (thin)
├── .github/copilot-instructions.md  # Copilot adapter (thin)
├── .gitattributes            # graphify-out/graph.json merge=graphify
├── .gitignore                # secrets + runtime artifacts policy
├── AGENTS.md                 # Codex/generic adapter (thin)
├── CLAUDE.md                 # Claude Code adapter (thin)
├── docs/
│   ├── architecture.md       # canonical target architecture (2468 lines, Spanish)
│   └── ai-engineering/       # AGENT_ARCHITECTURE, SKILL_CATALOG, ROUTING_RULES,
│                             #   CONTEXT_STRATEGY, VALIDATION
└── graphify-out/
    ├── README.md             # documents "0 code nodes" expectation for PRE-00
    └── cache/                # git-ignored local cache
```

## 3. Classification against the requested axes

### 3.1 Existing trading code

**None.** The only files in the repository are Markdown/MDC text. There is no strategy
code, no order handling, no position management, no broker interaction.

### 3.2 Experimental code

**None.** No code exists at all; nothing can be experimental yet.

### 3.3 Duplicated code

**None observed, by design.** The governance layer uses a canonical-source + thin-adapter
pattern: `.ai/` is the single source of truth and the four tool adapters
(`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-canonical.mdc`,
`.github/copilot-instructions.md`) explicitly forbid duplicating rules into themselves.

### 3.4 Dead code

**None.** No code exists. Documentation is internally consistent: `.ai/context/repo-map.md`
correctly describes the PRE-00 state and matches the on-disk reality verified in this
audit.

### 3.5 Infrastructure

**None implemented.** The target layout (`docs/architecture.md` §27) plans
`infra/compose` with postgres, redis, falkordb, minio, mlflow, langfuse, prometheus,
grafana — none exist yet.

**Present (development tooling only):**

- Graphify git hooks: `.git/hooks/post-commit` and `.git/hooks/post-checkout` (installed)
- `.gitattributes` merge driver for `graphify-out/graph.json`
- Graphify CLI installed and operational (verified this audit)

### 3.6 Execution integrations

**None.** The MT4 bridge (`QuantBridgeEA.mq4`, ZeroMQ gateway) is design-only
(`docs/architecture.md` §8, §9). No broker account, demo or real, is connected.

### 3.7 Data pipelines

**None.** Data architecture (PostgreSQL+TimescaleDB, Parquet/MinIO medallion layers,
Redis) is design-only (§13). No market data, no catalog, no ingestion.

### 3.8 Agent frameworks

The only "agents" present are the **static AI engineering governance layer** (`.ai/`):
12 specialist agent cards + 35 skills + rule-based routing. Important distinctions:

- This is **not** a runtime agent framework; it is development-time routing for AI
  coding assistants.
- Runtime frameworks are **explicitly prohibited**: "No RuFlo / Claude Flow /
  orchestration frameworks. Rule-based routing only" (`AGENTS.md`).
- Planned runtime agents (TradingAgents, RD-Agent, Graphiti) are design-only (§3, §4, §11).

### 3.9 Prompts

**Present:** agent cards and skills under `.ai/` define roles and procedures.
**Absent:** the production `prompts/` directory from the target layout (§27:
`analysts/`, `researchers/`, `trader/`, `evaluators/`) — no production prompts exist yet.

### 3.10 Tests

**None.** No `tests/` directory (target §27 lists unit, integration, replay, leakage,
backtest, execution, risk, security, chaos). Test **discipline** is already specified:
`docs/architecture.md` §30 and `.ai/rules/definition-of-done.md` (property-based risk
tests, leakage fail-on-violation, deterministic replay, idempotency).

---

## Addendum — Phase 0 Foundations implemented (2026-08-26)

The state above describes the repository at the PRE-00 audit. Phase 0 Foundations has
since been implemented; this addendum supersedes the superseded facts.

| Fact | New evidence |
|---|---|
| Code files | `core/` (domain, schemas, events, config, clock, audit), `apps/api` (FastAPI), `apps/worker`, `engines/*`, `adapters/*` — 42 Python source files; pyproject.toml (hatchling, Python ≥3.12), uv.lock, Makefile, CI workflow |
| Canonical contracts | All 20 domain contracts + `DomainEvent` envelope in `core/schemas` (schema_version, trace_id, produced_at UTC, provenance, deterministic JSON) — catalog `CANONICAL_CONTRACTS` |
| Virtual clock | `core/clock` — `SystemClock`, `VirtualClock` (deterministic, monotonic) |
| Event layer | `core/events` — canonical event registry (all §14 names), payload version migration chains, standard envelope |
| Tests | `tests/` per §27; 202 unit tests passing (validation, serialization, versioning, clock determinism, state transitions, import guard, config, audit, API) |
| Trading functionality | **Still none** — no external framework integrated (guard test enforces it for `core/`) |
| CI | `.github/workflows/ci.yml`: ruff + format check + mypy strict + pytest on Python 3.12 |
| Infra | `infra/compose/docker-compose.yml` (TimescaleDB, Redis, MinIO — pinned images) |
| Docs | `docs/architecture/PHASE0_FOUNDATIONS.md` records the implementation; `.ai/context/repo-map.md` updated |

Remaining phases 1–12 are unchanged and gated as per `IMPLEMENTATION_ORDER.md`.

### 3.11 Configuration

**Present:** `.gitignore`, `.gitattributes`, `.cursor/rules/00-canonical.mdc`,
`.github/copilot-instructions.md`.
**Absent:** all runtime configuration — no `Makefile`, no `.env.example`
(target §27 lists both), no `external-lock.yaml` (§28, INV-14), no compose files.

### 3.12 Secrets handling

**Policy present, secrets absent.** Evidence:

- `.gitignore`: `.env`, `.env.*`, `secrets/`, `*.key`, `*.pem` excluded;
  `!.env.example` explicitly allowed.
- Target policy (`docs/architecture.md` §29, INV-9): three trust zones; LLMs never hold
  broker credentials, MT4 credentials, execution sockets, or secret-store access.
  Dev: `.env`; prod: SOPS+age or Vault/Docker secrets. Never in git, Obsidian, Graphiti,
  Langfuse prompts, or logs.
- Audit verification: no `.env*`, key, or pem files exist in the working tree.

## 4. Documentation state

| Artifact | State |
|---|---|
| `docs/architecture.md` | **Complete** — 35 sections: vision, component decisions, modes, Risk Engine, MT4, reconciliation, kill switches, memory, point-in-time, data, event bus, domain objects, fusion, post-trade, strategy/validation factories, metrics, LLM eval, observability, Graphify/Obsidian, Command Center, repo layout, dependencies, security, testing, roadmap (Phases 0–12), V1 scope, 20 frozen decisions |
| `.ai/rules/architecture-invariants.md` | **Complete** — INV-1 … INV-16, cross-referenced to § sections |
| `docs/ai-engineering/` | **Complete** — team topology, skill catalog, routing matrix, context strategy, 10-scenario validation |
| `docs/ADR/` | **Was absent** — created by this task (16 ADRs for the frozen decisions) |
| `docs/architecture/` | **Was absent** — created by this task (this document + 3 siblings) |
| `docs/threat-model/`, `docs/runbooks/`, `docs/protocols/` | Absent — planned in §27, not started |

## 5. Verdict

The repository is **PRE-00: documentation-only**, exactly as `.ai/context/repo-map.md`
claims. Governance and target architecture are mature and internally consistent;
**100% of runtime implementation is pending**. There is nothing to migrate, delete, or
deduplicate. The next step is not code — it is ratifying the frozen decisions as ADRs
(this task) and then executing Phase 0 (Foundations) per
`docs/architecture/IMPLEMENTATION_ORDER.md`.
