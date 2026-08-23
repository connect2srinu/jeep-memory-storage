FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /application
COPY apps/reference-agent ./
RUN python -m pip install --no-cache-dir .

CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8000", "app"]
