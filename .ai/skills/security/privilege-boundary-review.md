---
name: privilege-boundary-review
description: "Review privilege boundaries: LLM vs Core vs Broker, API auth, secret-store access. Use when permissions, zones, or service accounts change."
---

# Privilege Boundary Review

## Purpose
Least privilege across the LLM → Core → MT4 chain (architecture §29).

## Trigger conditions
Authn/z changes, service account changes, new services, zone changes.

## Inputs
Component/permission design.

## Outputs
Privilege matrix audit.

## Related agents
`security` (owner), `infra-sre`, `principal-architect`.

## Procedure
1. Enumerate who can call what: LLM paths cannot touch execution or secrets (INV-9).
2. API auth: least privilege per role (Command Center vs workers vs research).
3. Network: only WireGuard path to MT4; ZeroMQ private only.
4. Service accounts per service, not shared.
5. Confirm mode changes (LIVE_AUTO etc.) require explicit admin action (§11 roadmap).
