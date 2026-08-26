---
name: dependency-tracing
description: "Trace imports, package dependencies, and data flow between modules. Use when a change may ripple, when a dependency is added or removed, or when an import chain looks suspicious."
---

# Dependency Tracing

## Purpose
Make dependency direction explicit and verify it respects the architecture
(core ← engines ← adapters, never inverted).

## Trigger conditions
Cross-module changes, new dependencies, import direction questions, pinning reviews.

## Inputs
The module/package under change.

## Outputs
Dependency list with direction and violations.

## Related agents
`principal-architect`, `security` (dependency-security is separate).

## Procedure
1. `graphify path <A> <B>` for module pairs.
2. Check direction against `.ai/rules/architecture-invariants.md` (INV-12..INV-15).
3. Flag cycles and domain bypasses (adapter importing engine internals, etc.).
4. New third-party deps must be pinned in `external-lock.yaml` (INV-14).
