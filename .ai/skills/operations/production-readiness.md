---
name: production-readiness
description: "Check a service or release is safe to deploy. Use before deployments and phase transitions."
---

# Production Readiness

## Purpose
Nothing goes to production without health checks, alerts, backups, and rollback.

## Trigger conditions
Deployments, new services, phase gates (especially anything near LIVE).

## Inputs
Release diff + runbooks.

## Outputs
Go/No-Go checklist verdict.

## Related agents
`infra-sre` (owner), `security`, `verification`.

## Procedure
1. Health checks + alert rules exist (observability-review).
2. Backups tested (restore drill), especially Postgres/MinIO.
3. Rollback plan documented.
4. Secrets handled per §29.
5. Runbook in `docs/runbooks/`.
6. For trading paths: reconciliation + kill-switch verified; SAFE_MODE entry tested.
7. Chaos scenarios exercised (§30) for execution-critical changes.
