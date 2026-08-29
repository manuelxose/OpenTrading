# ADR-0009: Graphify as development context tooling only

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ repository-intelligence skills as supporting)

## Context

The platform has two graph concepts that must never be confused. The decision was frozen
in `docs/architecture.md` §34.10 ("Graphify será contexto de desarrollo, no memoria
financiera") and is carried by INV-11 (Graphify ≠ Graphiti).

## Decision

**Graphify is adopted exclusively as development-time context tooling.** It indexes the
codebase (AST/tree-sitter) into `graphify-out/{graph.json, wiki/, GRAPH_REPORT.md}`, can
update only modified files, and supports a post-commit hook (§24). It lets coding agents
answer questions like "How does OrderIntent reach MT4?" without re-reading thousands of
files.

**Graphify is never part of the trading runtime** and never stores financial memory:

```text
Graphify = knowledge graph of the code
Graphiti = temporal knowledge graph of the trading
```

## Alternatives considered

- **Graphify as runtime trading memory** — rejected: INV-11; Graphify has no temporal
  validity, provenance, or `as_of` retrieval semantics (Graphiti's job, ADR-0008).
- **No code-index tooling** — rejected: the workspace policy (AGENTS.md/CLAUDE.md) and
  §24 rely on it to reduce repeated repository context; already installed with git hooks.
- **Commercial/L3 graph of code** — rejected: the repo standard is Graphify, installed
  and operational; switching requires a new ADR.

## Consequences

- Positive: cheap AST-only indexing (no LLM cost), shared `graph.json` committed for all
  agents, merge driver configured in `.gitattributes`.
- Negative: none for runtime; `graphify-out/` is a commit artifact that must remain
  dev-only.
- Follow-ups: run `graphify update .` after structural code changes; the graph is
  currently empty (0 code nodes) because the repo is docs-only — expected per
  `graphify-out/README.md`.

## Validation

- Frozen decision §34.10; §24 (obligatory separation); INV-11.
- Repo evidence: Graphify CLI installed; post-commit/post-checkout hooks present;
  `graphify extract . --code-only` verified "found 0 code, 69 docs" on 2026-08-26.
