---
name: event-contract-design
description: "Design or review domain events and their envelope. Use when adding, renaming, or changing events on the Redis Streams bus."
---

# Event Contract Design

## Purpose
Keep the event bus consistent and evolvable without breaking consumers.

## Trigger conditions
New event type, payload change, consumer/producer wiring.

## Inputs
Event name, payload schema, producers, consumers.

## Outputs
Envelope-compliant schema and migration notes.

## Related agents
`principal-architect` (owner), `backend-platform`.

## Procedure
1. Enforce envelope fields (schema_version, event_id, trace_id, event_time,
   ingested_at, producer, payload, provenance) — INV-15.
2. Name events per §14 vocabulary; don't invent near-duplicates.
3. Version payloads; define consumer compatibility for each change.
4. Trace `trace_id` end-to-end (snapshot → execution → postmortem) — §31.
