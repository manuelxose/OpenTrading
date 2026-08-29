# infra/mlflow — MLflow (experiment tracking, Phase 9)

- Custom image from `ghcr.io/mlflow/mlflow:v3.8.1` plus pinned
  `psycopg2-binary==2.9.12` + `boto3==1.43.80` (see Dockerfile).
- Metadata → Postgres database `mlflow`; artifacts → MinIO bucket
  `mlflow-artifacts`. Tracking UI on 127.0.0.1:5000.
