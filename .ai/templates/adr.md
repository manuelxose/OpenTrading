# ADR Template

Store in `docs/ADR/NNNN-lowercase-title.md` (4-digit sequence).

```markdown
# ADR-NNNN: Title

- Status: proposed | accepted | superseded by ADR-xxxx
- Date: YYYY-MM-DD
- Deciders: principal-architect (+ mandatory reviewers for the change class)

## Context
Why a decision is needed. Which architecture invariant or frozen decision is involved.

## Decision
The chosen option, precisely.

## Alternatives considered
Option, pros, cons, why rejected.

## Consequences
Positive, negative, risks, follow-ups.

## Validation
Evidence and checks that support the decision.
```

## When an ADR is required

- Changing any frozen decision (architecture §34) or invariant in
  `.ai/rules/architecture-invariants.md`.
- Introducing a new service, engine, or cross-service boundary.
- Changing the event envelope or a domain contract.
- Changing data store responsibilities (§13 split).
- Anything the Principal Architect classifies as architecture-wide.

## Process

1. Draft with template → 2. Principal Architect review → 3. mandatory reviewers for the
change class → 4. merge with implementation → 5. register in `docs/ADR/README.md` index.
