# Routing Validation — OpenTrading

Ten representative tasks run through the routing rules to verify: correct primary,
correct mandatory reviewers, and no unnecessary agents. Deterministic rule check
(no LLM needed for routing itself).

| # | Scenario | Primary | Supporting | Mandatory reviewers | Unnecessary agents avoided |
|---|---|---|---|---|---|
| 1 | Modify a Qlib factor | `quant-research` | `market-data` | `verification` (+ `market-data` if timestamps touched → data-time class) | `execution-mt4`, `security`, `infra-sre`, `command-center` |
| 2 | Change position sizing | `risk` | `trading-backtest` | `verification` (risk-sensitive) | `execution-mt4`, `ai-trading-systems`, `command-center` |
| 3 | Modify an MT4 order path | `execution-mt4` | `risk` | `security` + `verification` (execution-sensitive = execution + risk + security + verification; primary overlaps) | `quant-research`, `command-center`, `infra-sre` |
| 4 | Change Graphiti temporal retrieval | `ai-trading-systems` | `market-data` | `verification` (data-time class → market-data + quant-research + verification; quant-research joins as reviewer if memory feeds research inputs) | `execution-mt4`, `command-center`, `infra-sre` |
| 5 | Build a new dashboard screen | `command-center` | `backend-platform` if API contracts change | `verification` (substantial) | `risk` (unless risk visualization changes semantics), `execution-mt4` |
| 6 | Change PostgreSQL schema | `backend-platform` | `market-data` | `principal-architect` (domain contract) + `verification` | `execution-mt4`, `security` (unless auth tables), `ai-trading-systems` |
| 7 | Investigate poor backtest performance | `trading-backtest` | `quant-research` | `verification` | `risk` (unless sizing bug found), `security`, `command-center` |
| 8 | Diagnose broker reconciliation failure | `execution-mt4` | `backend-platform` | `risk` + `security` + `verification` (execution-sensitive) | `command-center`, `quant-research` |
| 9 | Change TradingAgents prompts | `ai-trading-systems` | `market-data` | `risk` + `security` + `verification` (LLM boundary) | `execution-mt4` (no broker path), `infra-sre` |
| 10 | Change system-wide architecture | `principal-architect` | affected domain agents (e.g. `risk`, `market-data`) | `verification` | uninvolved domain agents stay out |

## Checks performed

- **Correct primary:** each scenario's primary owns the touched domain per
  `ROUTING_RULES.md` primary matrix. ✔
- **Mandatory reviewers present:** change-class unions applied
  (`.ai/rules/cross-review-rules.md`). ✔
- **No unnecessary agents:** supporting agents limited to real dependencies; reviewers
  limited to change-class unions. ✔
- **No swarm:** one primary per scenario. ✔

## Verified by design (not yet executable)

Routing is declarative (this repository has no code yet, PRE-00). The rules are
machine-checkable: change-class detection keys on path prefixes and vocabulary
(`engines/risk/`, `mt4/`, `adapters/`, timestamps/`as_of`, prompts/retrieval), and
the reviewer unions are exact set operations. When code lands, these rules can be
enforced by a hook or CI check without adding an orchestration framework.
