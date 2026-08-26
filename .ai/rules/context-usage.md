# Context Usage Rules

Agents must not repeatedly consume the entire repository. Context priority:

1. **Graphify / context index** — `graphify query`, `graphify path`, `graphify explain`
   before raw file browsing. Skip only for confirmed trivial isolated edits or formatting.
2. **Architecture documentation** — `docs/architecture.md`, `docs/ai-engineering/`.
3. **Relevant files** — the files the task actually touches.
4. **Dependency neighborhood** — `graphify path <A> <B>` to see relationships before
   expanding scope.
5. **Broader exploration** — only when the above are insufficient.

## Maintenance

- After material structural changes (new packages, moved modules, new services):
  run `graphify update .` (or the configured hook does it on commit).
- A stale graph is a reason to update it, not to abandon it.

## Budget discipline

- Use the smallest relevant skill body; load one skill at a time.
- Pass bounded subgraphs to collaborators instead of whole reports.
- Do not sacrifice correctness to save tokens: risk, execution and leakage checks
  deserve extra context. When in doubt, read the file.
