# Adversarial Verification Workflow

The Verification agent must actively try to prove the implementation wrong.
It does not rubber-stamp.

1. **Re-read the task and its change class.** Confirm the primary agent and reviewers
   from `docs/ai-engineering/ROUTING_RULES.md`. If a mandatory reviewer was skipped,
   that is already a CHANGES_REQUIRED finding.

2. **Re-run the gates yourself.** Do not trust the implementer's output:
   - lint / typecheck / unit / integration commands, with fresh results;
   - domain evidence: leakage tests, deterministic replay, property-based risk tests,
     idempotency/reconciliation/chaos tests as applicable.

3. **Attack the invariants** (`.ai/rules/architecture-invariants.md`):
   - any LLM path with authority over capital? (INV-1)
   - non-`OrderIntent` crossing object, divergent backtest/paper/live logic? (INV-2)
   - any query in simulated context without `as_of`, any future data path? (INV-3)
   - any non-deterministic, LLM-touched, or reason-code-less risk path? (INV-4)
   - intelligence creeping into MQL4, EA validation holes? (INV-5)
   - missing reconciliation path on restart? (INV-6)
   - kill/dead-man gaps? (INV-7)
   - mode or promotion lifecycle bypass? (INV-8)
   - zone violations, secrets near LLM path? (INV-9)
   - data store misuse? (INV-10)
   - Graphify/Graphiti conflation? (INV-11)
   - frozen decision changed without ADR? (INV-12)
   - runtime merge? (INV-13)
   - unpinned dependency? (INV-14)
   - event missing envelope fields? (INV-15)
   - arbitrary fusion weights? (INV-16)

4. **Hunt for fakes.** Mocks, stubs, `NotImplementedError`, hardcoded returns left in
   production paths; tests that only assert mocks; coverage theater.

5. **Security & performance scan.** Threat model impact, secrets, boundary review;
   obvious performance regressions in hot paths.

6. **Verdict** per `.ai/templates/review-report.md`:
   APPROVED (evidence) / CHANGES_REQUIRED (blocking findings with acceptance criteria) /
   BLOCKED (name the exact blocker).

Do not approve because the code "looks reasonable". Approve because it survived the attack.
