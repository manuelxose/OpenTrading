# vault-trading/ — Obsidian human knowledge mirror (architecture §25)

This vault is a human-readable, best-effort mirror. It is never a source of trading
truth, and trading continues normally if the vault is missing or unwritable.

The worker initializes `00_System` through `90_Auto` and exports canonical events for
trades, postmortems, strategies, experiments, risk incidents, and research conclusions
with confidence >= 0.8. Every generated note carries canonical IDs, event/trace IDs,
and an automatic-generation warning. Payloads containing secret-like fields or values
are rejected before any file is written (INV-9).

Authoritative records remain in PostgreSQL/TimescaleDB and the other purpose-specific
stores defined by INV-10. Attachments are git-ignored.
