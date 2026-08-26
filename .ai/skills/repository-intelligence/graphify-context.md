---
name: graphify-context
description: "Use the Graphify codebase knowledge graph (graphify-out/) to get bounded subgraphs instead of re-reading the repo. Use before broad exploration of architecture, dependencies, or cross-file relationships."
---

# Graphify Context

## Purpose
Replace repeated large file reads with targeted graph queries. Graphify is development
context ONLY — never trading memory (INV-11).

## Trigger conditions
Any codebase question beyond a trivial isolated edit; dependency tracing; impact analysis.

## Inputs
Question in natural language, two symbols for `path`, or a concept for `explain`.

## Outputs
Bounded subgraph with the relevant nodes/edges.

## Related agents
All.

## Procedure
1. `graphify query "<question>"` (or `path` / `explain`).
2. Use `graphify-out/wiki/` for broad navigation.
3. After structural changes: `graphify update .` so the graph stays current.
4. Never read the full `GRAPH_REPORT.md` when a query suffices.
