# Runbook — Secrets management (SOPS + age)

Canonical decisions: `docs/architecture.md` §29, ADR-0025, `.ai/rules/architecture-invariants.md`
INV-9. Implementation: `.sops.yaml`, `scripts/secrets/*`.

## Policy

- Production secrets live **only** in `secrets/*.env`, encrypted with SOPS + age.
- Runtime receives secrets **only** through environment variables (`OT_*` and the
  compose `*_PASSWORD`/`*_KEY` variables). The code never reads SOPS files directly
  (INV-9: secrets are read from the environment only).
- Never store secrets in: Git, Obsidian, Graphiti memory, Langfuse prompts, or logs.
  Log redaction is enforced by `core/security/redact.py` for LLM worker processes.
- Development uses placeholder values from `.env.example` (`opentrading-dev` …) that
  are **not** secrets — they exist only so the dev stack boots without ceremony.

## One-time setup

```bash
# 1. Create the host age identity (private key stays in ~/.config/sops/age/keys.txt)
scripts/secrets/setup-age.sh

# 2. Add the printed public key to your deployment: it becomes the SOPS recipient
#    for `secrets/*.env`. Operators who must decrypt need their own age public key
#    added to the recipient list too (SOPS supports multiple --age recipients).
```

The `age:` field in `.sops.yaml` is a placeholder; recipient keys are always passed
on the command line by the scripts, so no key material is committed.

## Encrypting / decrypting

```bash
# Encrypt in place (dotenv): values become SOPS-wrapped, keys stay visible
scripts/secrets/encrypt.sh secrets/.env.prod

# Decrypt in place (only for inspection; re-encrypt afterwards)
scripts/secrets/decrypt.sh secrets/.env.prod

# Run a command with secrets injected via environment — no plaintext on disk:
sops exec-env --input-type dotenv secrets/.env.prod \
  'uv run python -m engines.execution.cli live-gated'
```

## Production compose

Docker Compose reads plain env files, so materialize a transient plaintext copy
(`secrets/` is git-ignored), start the stack, then remove it:

```bash
sops decrypt --input-type dotenv --output-type dotenv \
  secrets/.env.prod > secrets/.env.prod.plain
docker compose --project-name opentrading-prod \
  -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.prod.yml \
  --env-file secrets/.env.prod.plain up -d --build --wait
shred -u secrets/.env.prod.plain   # or: rm -f (filesystem-dependent)
```

Generate values with `openssl rand -hex 32` (hex only — safe inside the SQL used by
`infra/postgres/init/002-roles.sh`, which rejects quotes).

## Secret inventory (production)

| Variable(s) | Consumer | Notes |
|---|---|---|
| `OT_LIVE_APPROVAL_SIGNING_KEY`, `OT_LIVE_OPERATOR_TOKEN` | API + live runtime | Human gate. Missing → LIVE_GATED refuses to start |
| `POSTGRES_PASSWORD` | superuser | Admin/backups only; never in app DSNs |
| `POSTGRES_MIGRATOR_PASSWORD`, `POSTGRES_APP_PASSWORD`, `POSTGRES_READONLY_PASSWORD` | Alembic / apps / Grafana+exporters | Roles created by `002-roles.sh` |
| `LANGFUSE_DB_PASSWORD`, `MLFLOW_DB_PASSWORD` | Langfuse, MLflow | Own their databases only |
| `REDIS_PASSWORD`, `REDIS_EXPORTER_PASSWORD` | apps / redis-exporter | ACL users |
| `MINIO_ROOT_PASSWORD` | MinIO admin | Never used by apps |
| `MINIO_APP_ACCESS_KEY/SECRET_KEY`, `MINIO_LANGFUSE_ACCESS_KEY/SECRET_KEY`, `MINIO_MLFLOW_ACCESS_KEY/SECRET_KEY` | platform / Langfuse / MLflow | Scoped per-bucket policies |
| `FALKORDB_PASSWORD` | Graphiti adapter | `requirepass` |
| `LANGFUSE_*` (NextAuth, salt, encryption, init keys) | Langfuse | Self-hosted instance secrets |
| Broker / MT4 credentials | **Nothing in this repo** | Live on the MT4 side only (§29) |

## Rotation

1. Generate new values; encrypt into `secrets/*.env`.
2. Rotate per-store: `ALTER ROLE … PASSWORD`, `mc admin user …`, Redis `ACL SETUSER`,
   FalkorDB restart with new `FALKORDB_PASSWORD`.
3. Restart consumers with `sops exec-env`.
4. Verify: `scripts/secrets/verify.sh` + one integration smoke (`make test-integration`).

## Verification

```bash
scripts/secrets/verify.sh          # git-ignore + committed-file checks (+ gitleaks if installed)
git check-ignore .env .env.prod secrets   # must print the paths
```

CI: gitleaks on every push/PR (`.github/workflows/ci.yml`), allowlist limited to dev
placeholders (`.gitleaks.toml`).
