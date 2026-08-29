# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python 3.12 FastAPI backend with a TypeScript React command center. The browser consumes
versioned read-only APIs and never connects directly to persistence or execution services.

## Users

Trading operators, quantitative researchers, and risk owners monitoring the autonomous
platform during research, backtest, paper, and live-gated operation.

## Product Purpose

OpenTrading researches, evaluates, executes, and reviews quantitative trading strategies.
The Command Center makes the complete operating state and every trade decision chain visible
without requiring terminal logs.

## Positioning

Every decision is reconstructable from source data through research, deterministic fusion and
risk, execution, lifecycle, and postmortem while intelligence remains separated from authority
over capital.

## Operating Context

Desktop-first continuous monitoring with mobile access for incident checks. Operators need fast
status scanning, explicit freshness, and drill-down into immutable decision evidence.

## Capabilities and Constraints

- Sections: Overview, Research, Signals, Risk, Orders, Trades, Positions, Backtests, Memory,
  Agents, and System.
- PostgreSQL is transactional truth; dependency health is probed by the API.
- The frontend contains no trading, risk, sizing, fusion, or execution business logic.
- Unavailable platform capabilities are represented honestly, never with synthetic data.

## Evidence on Hand

Canonical schemas, pipeline contexts, execution state, paper accounts, post-trade reviews, and
dependency readiness probes exist in the repository. No marketing claims or customer evidence
should be invented.

## Product Principles

- Truth before decoration.
- Operational status must be legible in seconds.
- Every trade must be explainable end to end.
- Intelligence proposes; deterministic systems decide capital.
- Empty and degraded states are first-class operational information.

## Accessibility & Inclusion

The web interface must be keyboard operable, responsive down to mobile widths, preserve visible
focus, and never rely on color alone for status.
