# Task Routing Workflow

The developer should not normally have to name agents. Apply this loop to every task.

```text
task
  → classify affected domains & change class
  → load repository context (Graphify first)
  → select primary specialist
  → select mandatory reviewers
  → load primary's skills (+ reviewer skills)
  → execute under Definition of Done
  → Verification review (substantial tasks)
  → report
```

## Step 1 — Classify

- Domains touched: research/data/trading/risk/execution/LLM/backend/frontend/infra/security.
- Change class: `.ai/rules/cross-review-rules.md`
  (risk-sensitive / execution-sensitive / data-time / LLM-boundary / architecture-wide).
- Scope: file / component / package / cross-cutting / architecture-wide.
- Risk level: low / medium / high / critical.

## Step 2 — Context

Follow `.ai/rules/context-usage.md`: Graphify query first, architecture docs second,
then the files. Pass bounded subgraphs to collaborators.

## Step 3 — Primary specialist

Look up the task type in `docs/ai-engineering/ROUTING_RULES.md` (authoritative matrix).
Exactly one primary agent owns the work.

## Step 4 — Mandatory reviewers

Union of reviewer sets for each change class the task belongs to. Reviewers are not
implementers; they review when the primary claims the work is ready.

## Step 5 — Skills

Load the skills owned by the primary agent (listed in its agent card). Load reviewer
skills only at review time. One skill at a time; smallest relevant body.

## Step 6 — Execute

Definition of Done gates apply progressively, not at the end:
`.ai/rules/definition-of-done.md`.

## Step 7 — Verify

Substantial tasks require the `verification` agent to attempt to break the result
(`.ai/workflows/verification-workflow.md`).

## Step 8 — Report

Primary reports via `.ai/templates/agent-output.md`; verification via
`.ai/templates/review-report.md`.

## Anti-swarm rule

Do not instantiate the full team for small tasks. Multi-agent collaboration only where
multiple specialist perspectives materially improve correctness (risk/execution/security
boundaries). One primary by default.
