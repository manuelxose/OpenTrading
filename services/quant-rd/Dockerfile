FROM python:3.11.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/opentrading

RUN groupadd --system quant && useradd --system --gid quant --home /workspace quant
WORKDIR /opt/opentrading
COPY services/quant-rd/requirements.txt /tmp/quant-rd/requirements.txt
RUN python -m pip install --no-cache-dir --requirement /tmp/quant-rd/requirements.txt
COPY core ./core
COPY adapters/qlib ./adapters/qlib
COPY adapters/rdagent ./adapters/rdagent
COPY services/quant_rd ./services/quant_rd
RUN mkdir -p /workspace /outputs && chown -R quant:quant /workspace /outputs
USER quant
WORKDIR /workspace
ENTRYPOINT ["python", "-m", "services.quant_rd.bootstrap"]
CMD ["fin_quant"]
