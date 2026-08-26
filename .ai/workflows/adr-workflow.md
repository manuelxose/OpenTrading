# ADR Workflow

ADRs are required for any change to frozen decisions, architecture invariants, service
boundaries, event contracts, or data responsibilities. See `.ai/templates/adr.md`.

```text
decision need
  → draft ADR (template)
  → principal-architect review
  → mandatory reviewers for the change class
  → accept / amend / reject
  → register in docs/ADR/README.md
```

- An ADR documents a decision with consequences; it is not a change log.
- Frozen decisions (architecture §34) require ADR **before** implementation, not after.
- If a task silently violates a frozen decision without an ADR, Verification must
  issue CHANGES_REQUIRED regardless of code quality.
