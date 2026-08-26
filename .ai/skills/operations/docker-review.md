---
name: docker-review
description: "Review Docker/Compose changes. Use when compose files, images, networking, or volumes change."
---

# Docker Review

## Purpose
Reproducible, least-privilege containers with correct networking (architecture §27, §29).

## Trigger conditions
`infra/compose` changes, Dockerfiles, network/volume changes.

## Inputs
Compose/Dockerfile diff.

## Outputs
Findings + verification steps.

## Related agents
`infra-sre` (owner), `security`.

## Procedure
1. Services pinned to explicit image tags; no `latest` (INV-14).
2. Networks: ZeroMQ/MT4 traffic private only; no ports exposed to internet (INV-9).
3. Volumes for persistent data (Postgres, MinIO, FalkorDB) with backups defined.
4. Health checks per service; restart policies explicit.
5. No secrets baked into images or compose env (secret-scan).
