# ADR-0006: RD-Agent as the autonomous R&D factory (offline)

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ quant-research primary; ai-trading-systems if
  LLM-facing paths involved)

## Context

The platform aims at continuous, autonomous research (Phase 12). The decision was frozen
in `docs/architecture.md` §34.6 ("RD-Agent será la fábrica autónoma de I+D") with the
modifier **ADOPT OFFLINE** (§2, §4).

## Decision

**Adopt Microsoft RD-Agent as the autonomous factor/model/hypothesis R&D factory**,
running in the Quant R&D runtime (Python 3.11, Linux) behind `adapters/rdagent`.

Its loop is the R&D chain (§4): generate hypothesis → factor/model → experiment → write
implementation → run → analyze → feedback → new hypothesis. RD-Agent may invent and
implement factors, create/compare models, run experiments, produce `StrategyCandidate`s,
detect model degradation, suggest hypotheses, and open PRs with improvements.

**It may not:** change risk limits, modify production directly, change the MT4 bridge,
activate LIVE_AUTO, deploy strategies with money, or replace an approved strategy without
the promotion gate (§4, §18). There is no `RD-Agent → LIVE` edge (INV-8).

## Alternatives considered

- **RD-Agent wired to production** — rejected: violates INV-1/INV-8 and §4's forbidden
  list; research autonomy must never become capital authority.
- **Manual research only** — rejected: Phase 12 (continuous quant firm) is an explicit
  roadmap goal; RD-Agent is the selected mechanism.
- **A different autonomous research framework** — rejected: §2/§34.6 froze RD-Agent;
  changing it would require a new ADR (INV-12).

## Consequences

- Positive: a proven hypothesis→factor→model→feedback chain without building one.
- Negative: many candidate experiments multiply false-positive risk — countered by
  mandatory multiple-testing protection and logging of failed experiments (§19), and
  by the Validation Factory gating every promotion.
- Follow-ups: Phase 9 (factory active) and Phase 10 (promotion gate) realize the
  candidate pipeline; reproducible experiments are Phase 9's DoD.

## Validation

- Frozen decision §34.6; §4 (loop, allowed/forbidden lists, runtime split); §18
  lifecycle without an RD-Agent→LIVE edge.
- `.ai/agents/quant-research.md`: "never touches risk limits or production".
- Repo evidence: no RD-Agent code yet (PRE-00).
