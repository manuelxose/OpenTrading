---
name: repository-navigation
description: "Find files, modules, and entry points in this repo efficiently. Use when exploring unfamiliar parts of the codebase, locating a symbol, or mapping how to get somewhere."
---

# Repository Navigation

## Purpose
Locate code efficiently using graph context first, then targeted reads.

## Trigger conditions
"Where is X", "how do I reach Y", unfamiliar modules, onboarding into a package.

## Inputs
Symbol/path/feature name; optional `graphify query`.

## Outputs
Short list of files and entry points with the reasoning path.

## Related agents
All; primary users `principal-architect`, `backend-platform`.

## Procedure
1. `graphify query "<feature>"` / `graphify path <A> <B>` first.
2. Read `docs/architecture.md` §27 for the canonical layout.
3. Read only the files on the path; do not dump whole directories.
