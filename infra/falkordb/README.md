# infra/falkordb — FalkorDB + Graphiti (temporal semantic memory, Phase 3)

- Image: `falkordb/falkordb:v4.20.4-alpine` (pinned), volume `falkordb-data`.
- Internal port 6379; published to 127.0.0.1:6380 (Redis owns host 6379).
- Graphiti (pinned `graphiti-core[falkordb]==0.29.3`, see external-lock.yaml)
  connects through `adapters/graphiti` — the store is provisioned here and
  accessed exclusively by that adapter (INV-10: memory lives only here).
  Point-in-time retrieval is enforced by the adapter's repository layer
  (`Memory.search(query, as_of=T)`), never trusted to the database alone.
