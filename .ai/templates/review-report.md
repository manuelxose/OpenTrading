# Verification Review Report

The Verification agent is adversarial: it must try to prove the implementation wrong.

```markdown
## Verdict
APPROVED | CHANGES_REQUIRED | BLOCKED

## Task under review
Goal, primary agent, change class, files affected.

## Evidence checked
- [ ] DoD gates verified (list commands re-run and results)
- [ ] Architecture invariants checked (cite INV-n)
- [ ] Change-class reviewers satisfied (risk / security / market-data / ai-systems / architect)
- [ ] No mock/stub/placeholder in production paths
- [ ] No leakage / determinism / idempotency violations
- [ ] Security implications (trust zones, secrets, boundaries)
- [ ] Performance implications
- [ ] No unrelated regressions

## Findings
Numbered findings, severity, file, evidence.

## Residual risks
What remains unverified and why.

## Required changes (if any)
Blocking items with acceptance criteria.
```

## Rules

- Approval requires re-run evidence, not the implementer's claims.
- If a mandatory reviewer was skipped, the verdict is CHANGES_REQUIRED at minimum.
- A BLOCKED verdict must name the exact blocking item and who can resolve it.
