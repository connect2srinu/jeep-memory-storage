FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /application
COPY apps/memory-agent ./
RUN python -m pip install --no-cache-dir .

EXPOSE 8000

# Use the serve launcher, not plain `adk web`: it registers the async Postgres scheme so
# short-term sessions land in Postgres instead of silently falling back to SQLite.
CMD ["sh", "-c", "HOST=0.0.0.0 PORT=${PORT:-8000} python -m memory_agent.serve"]
