---
name: dependency-security
description: "Review and pin dependencies. Use when adding or upgrading any dependency."
---

# Dependency Security

## Purpose
Pinned, reviewed dependencies only; production never follows main/latest/HEAD
(architecture §28, INV-14).

## Trigger conditions
New dependency, version bump, lockfile change.

## Inputs
Dependency + proposed version.

## Outputs
Pinning entry + risk verdict.

## Related agents
`security` (owner), `principal-architect`.

## Procedure
1. Record in `external-lock.yaml`: project, repository, tag, commit SHA, license,
   last reviewed.
2. Check license compatibility (TradingAgents Apache-2.0, Qlib MIT, Nautilus LGPL-3.0
   kept independent — §28).
3. Run vulnerability scan; review changelog for the range.
4. Verify no source is copied into core violating license boundaries.
