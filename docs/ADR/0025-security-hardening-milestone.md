# ADR-0025 — Security hardening milestone: trust zones, least privilege, secret lifecycle

- Status: accepted
- Date: 2026-08-28
- Deciders: principal-architect + security (execution-sensitive routing)
- Supersedes: none. Codifies architecture §29 into operational controls.

## Context

`docs/architecture.md` §29 defines three trust zones (Internet/LLM/market data → Core Quant
Platform → Broker/MT4) and forbids LLM processes from holding broker credentials, MT4
credentials, execution sockets, or secret-store access. The platform needed the §29
declarations turned into enforceable configuration, code, CI and tests, with an explicit
Definition of Done:

> A compromised LLM worker cannot directly submit a broker order.

## Decision

1. **Threat model is a living document.** `docs/threat-model/threat-model.md` is the
   authoritative register: zones, assets, actors, STRIDE table, controls C1–C13, and
   DoD traceability. Security changes must update it.
2. **Process-level zone enforcement.** New `core/security/zones.py` provides
   `assert_llm_process_cannot_execute()`; every LLM-facing entrypoint (`apps.worker`)
   calls it before wiring any dependency. LLM processes may never run in `LIVE_GATED`
   or `LIVE_AUTO`.
3. **Secret lifecycle = SOPS + age.** Production secrets live only in `secrets/*.env`
   encrypted with SOPS + age (`.sops.yaml`, `scripts/secrets/*`). Runtime reads secrets
   only from the environment (`OT_*`), preserving INV-9. Secrets never enter Git,
   Obsidian, Graphiti memory, Langfuse prompts, or logs; logs are redacted by
   `core/security/redact.py`.
4. **Least-privilege data stores.**
   - PostgreSQL: `ot_migrator` (DDL/migrations), `ot_app` (DML on business tables),
     `ot_readonly` (SELECT for Grafana/exporters); `langfuse` and `mlflow` own only
     their own databases. Alembic uses `OT_POSTGRES_MIGRATOR_DSN` when set.
   - Redis: ACL users (`opentrading` without `@admin/@dangerous/@scripting`,
     `redis-exporter` read-only); `requirepass`; protected mode.
   - MinIO: scoped users with per-bucket policies (`platform`, `langfuse`, `mlflow`);
     root credentials are admin-only.
   - FalkorDB: mandatory `requirepass`.
5. **Network segmentation.** Production compose publishes no ports and marks the
   internal network `internal: true`. Remote Windows MT4 is reachable only through
   WireGuard (`infra/wireguard/`, `docs/runbooks/mt4-wireguard.md`); ZeroMQ is never
   internet-exposed.
6. **CI security gates.** Gitleaks (secret scanning) and pip-audit (dependency
   auditing) run on every push/PR; Dependabot watches pip, GitHub Actions and Docker
   dependencies. A gitleaks allowlist covers dev placeholders only.
7. **Regression tests.** `tests/security/` encodes the zone invariants: worker cannot
   start in live modes, worker never imports the MT4 execution client, live client
   fails closed without an authorizer, secrets are masked, redaction works.

## Consequences

- Positive: LLM compromise is contained to Zone-1 advisory output + scoped worker
  stores; the execution boundary is enforced in code, configuration, CI and tests.
- Negative: more moving parts (roles, ACLs, users) increase operational surface;
  mitigations are documented in `docs/runbooks/secrets-management.md`,
  `docs/runbooks/infrastructure.md` and `docs/runbooks/mt4-wireguard.md`.
- Residual: a human with host access and secret-store keys can still cross zones
  (audit logging + review gates remain the control); CurveZMQ transport encryption
  remains an optional follow-up (threat T-16).
