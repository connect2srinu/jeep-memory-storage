FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/apps/memory-api/app

WORKDIR /workspace

COPY pyproject.toml README.md ./
COPY app ./app
COPY config ./config
COPY apps/memory-api ./apps/memory-api

RUN python -m pip install --no-cache-dir -e . -e 'apps/memory-api'

EXPOSE 8080

CMD ["sh", "-c", "alembic -c apps/memory-api/alembic.ini upgrade head && uvicorn memory_api.main:app --host 0.0.0.0 --port 8080"]
