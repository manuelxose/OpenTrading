# infra/langfuse — Langfuse (AI observability, Phase 2)

- Web + worker: `docker.langfuse.com/langfuse/langfuse{,-worker}:v4.19.0`
  (pinned). UI on 127.0.0.1:3000.
- Reuses platform Postgres (database `langfuse`), Redis, and MinIO (bucket
  `langfuse`); dedicated ClickHouse `25.12.11` for analytics storage.
- Dev bootstrap credentials come from `LANGFUSE_INIT_*` in `.env.example`.
- The Python v4 SDK reads `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and
  `LANGFUSE_HOST`. Without both keys tracing is a no-op and trading behavior is
  unchanged. Inputs/outputs are deliberately summarized; secrets and full
  research prose are not sent to telemetry.
