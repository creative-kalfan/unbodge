FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/packages

# Non-root runtime user (least privilege for the API/worker processes).
RUN useradd --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY pyproject.toml README.md ./
COPY packages/ ./packages/

RUN pip install --no-cache-dir "pydantic>=2.0" "packaging>=23" \
    "fastapi>=0.100" "uvicorn>=0.20" "httpx>=0.24" \
    "psycopg2-binary>=2.9" "redis>=4.0" \
 && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
