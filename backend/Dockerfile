# One image, two roles (ADR-0002: trading is a scheduled single pass, not a daemon):
#   - Cloud Run Service: runs the FastAPI app (default CMD below).
#   - Cloud Run Jobs: same image, command overridden per job to `loom trade-pass`,
#     `loom screen-insights`, `loom research-insights`, or `loom reconcile` — see
#     infra/gcp/setup.sh, which creates one Job per CLI command and a Cloud Scheduler
#     entry that triggers each on its own cadence.
FROM python:3.11-slim AS base

WORKDIR /app

# psycopg[binary] avoids needing libpq-dev at build time; kept minimal on purpose.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY loom ./loom
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir .

# Don't run as root — Cloud Run doesn't require it, and there's no reason this process needs it.
RUN useradd --create-home --shell /usr/sbin/nologin loom
USER loom

# Cloud Run injects PORT; uvicorn must bind to it, not a hardcoded port.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn loom.api.main:app --host 0.0.0.0 --port ${PORT}"]
