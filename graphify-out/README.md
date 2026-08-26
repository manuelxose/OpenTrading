# graphify-out — codebase knowledge graph (dev context only)

Graphify indexes the **code** for development context. It is never trading memory —
that is Graphiti (INV-11).

## Current state

PRE-00: the repository contains documentation only, so the code graph is empty
(0 code nodes). The graph will populate automatically as code lands.

## Commands

- Build/refresh (AST-only, no LLM cost):
  `graphify extract . --code-only && graphify cluster-only .`
- Incremental update after edits: `graphify update .`
  (a post-commit git hook is installed and updates the graph on every commit).
- Query: `graphify query "<question>"`, `graphify path A B`,
  `graphify explain "Symbol"`.

## Layout

- `graph.json` — committed, shared by all agents.
- `wiki/`, `GRAPH_REPORT.md` — generated navigation artifacts (committed).
- `cache/` — local cache (git-ignored).

See also `docs/ai-engineering/CONTEXT_STRATEGY.md`.
