# Deploy & test instructions (Phase 4)

## Local test (no credentials, offline-safe)

```bash
pip install -e ".[dev]" fastapi httpx uvicorn psycopg2-binary redis
PYTHONPATH=packages python -m pytest -q
```

Docker-backed tests run when a daemon + `python:3.11-slim` exist,
otherwise skip explicitly. Credential-gated tests (Nebius, Tavily,
LangSmith, Temporal) always skip/fail-closed without creds.

Optional live backends (this session measured both):

```bash
docker run -d --name unbodge-pg -e POSTGRES_PASSWORD=unbodge \
  -e POSTGRES_DB=unbodge -p 5433:5432 postgres:15-alpine
docker run -d --name unbodge-redis -p 6380:6379 redis:7-alpine
UNBODGE_TEST_POSTGRES_DSN="dbname=unbodge user=postgres password=unbodge host=127.0.0.1 port=5433" \
UNBODGE_TEST_REDIS_URL="redis://127.0.0.1:6380/0" python -m pytest -q
```

## Services

```bash
docker compose up --build        # api (:8000, incl. /ui/*), worker, postgres, redis
docker compose run worker python -m workflow.cli /jobs/job.json
```

GitHub Actions (`.github/workflows/ci.yml`) runs 3.11 + 3.14 with no
secrets. Temporal server and Nebius executors are documented extension
points, not provisioned here (see `workflow/temporal.py`, `docs/NEBIUS.md`).
