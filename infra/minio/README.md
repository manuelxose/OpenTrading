# infra/minio — MinIO + Parquet catalog (heavy history: /raw /bronze /silver /gold)

- Image: `minio/minio:RELEASE.2025-09-07T16-13-09Z` (pinned).
- Buckets bootstrap: the `minio-init` service (profile `init`, run by `make up`)
  creates `raw`, `bronze`, `silver`, `gold`, `mlflow-artifacts`, `langfuse`,
  `posttrade-artifacts` (post-trade learning loop).
- S3 API on 127.0.0.1:9000, console on 127.0.0.1:9001.
