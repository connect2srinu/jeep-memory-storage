FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/apps/control-plane-api/app

WORKDIR /workspace

COPY apps/control-plane-api ./apps/control-plane-api

RUN python -m pip install --no-cache-dir -e 'apps/control-plane-api'

EXPOSE 8080

CMD ["sh", "-c", "uvicorn control_plane_api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
