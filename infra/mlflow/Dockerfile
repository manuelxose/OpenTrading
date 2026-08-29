# MLflow tracking server image for OpenTrading.
#
# The upstream image (ghcr.io/mlflow/mlflow) ships without the Postgres and S3
# drivers we need. Baking pinned drivers here keeps every startup reproducible
# and offline (INV-14: no `pip install` at container runtime).
#
# Build (automatic via `make up`):
#   docker build --build-arg MLFLOW_VERSION=v3.8.1 -t opentrading/mlflow:v3.8.1 .

ARG MLFLOW_VERSION=v3.8.1
FROM ghcr.io/mlflow/mlflow:${MLFLOW_VERSION}

RUN pip install --no-cache-dir \
    "psycopg2-binary==2.9.12" \
    "boto3==1.43.80"
