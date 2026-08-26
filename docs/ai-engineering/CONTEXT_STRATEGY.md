# Context Strategy — OpenTrading

Goal: agents get the minimum context needed for correctness, with graph-first
navigation and explicit escalation when correctness demands more.

## Priority order

1. **Graphify / context index** — `graphify query` / `path` / `explain` before raw
   file browsing (`graphify-out/`). Skip only for confirmed trivial isolated edits or
   formatting.
2. **Architecture documentation** — `docs/architecture.md` (product) and
   `docs/ai-engineering/` (AI team). The product doc is long (2468 lines); read
   sections by topic, not whole file.
3. **Relevant files** — the files the task actually touches.
4. **Dependency neighborhood** — `graphify path <A> <B>` to see relationships before
   expanding scope.
5. **Broader exploration** — only when 1–4 are insufficient.

## Cheap context bootstrap

Before reading anything else, agents may load:

- `.ai/context/repo-map.md` — current repo state + target layout.
- `.ai/context/domain-glossary.md` — canonical vocabulary (OrderIntent, SAFE_MODE,
  modes, events, zones).
- `.ai/rules/architecture-invariants.md` — INV-1..INV-16.

Together these are a few hundred lines and replace repeated re-reading of the big
architecture doc for most routing decisions.

## Graphify policy

- Graphify = development-time codebase knowledge only. Never trading memory (INV-11).
- Use `graphify query` with a budget for large questions; `path` for relationships;
  `explain` for focused concepts.
- After material structural changes run `graphify update .` (or rely on the
  post-commit hook).
- A dirty/stale `graphify-out/` is a reason to update, not to abandon the graph.

## Token discipline

- Load one skill body at a time, smallest relevant skill.
- Pass bounded subgraphs to collaborators, not full reports.
- Do not read the whole `GRAPH_REPORT.md` when a query suffices.

## Correctness override

Risk, execution, leakage, and security-sensitive work may consume extra context by
design. When evidence is ambiguous: read the file. Never guess limits, protocol
fields, or data semantics.
