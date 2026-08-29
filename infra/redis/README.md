# infra/redis — Redis (cache, locks, Streams event bus, INV-15)

- Image: `redis:7.4-alpine` (pinned), AOF persistence, volume `redis-data`.
- Password always set (`REDIS_PASSWORD`, dev default `opentrading-dev`).
- Streams (§14 event bus) and consumer groups land with the worker phases.
