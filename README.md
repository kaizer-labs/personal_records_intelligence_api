# Personal Records Intelligence API

FastAPI backend for the Personal Records Intelligence MVP.

## Setup

From inside this repo:

```bash
cd /Users/kaizer/Desktop/personal_records_intelligence/personal_records_intelligence_api
docker compose up --build
```

API endpoints:

- `http://localhost:8000/health_check`
- `http://localhost:8000/docs`

UI:

- `http://localhost:5173`

## What Exists Today

- `GET /health_check`
- embedded DuckDB setup with startup initialization
- OpenAPI docs at `/docs`
- Dockerfile for local containerized development
- `docker-compose.yml` for API-local orchestration of backend plus sibling UI
- AI-friendly repository markdown files for onboarding and safe iteration

## Docs

- `docs/architecture.md`
- `docs/low-level-architecture.md`
- `docs/duckdb-setup.md`
- `docs/docker-setup.md`
- `docs/api-contract.md`
- `docs/development-workflow.md`

## Project Layout

- `app/main.py`: FastAPI app factory and middleware
- `app/api/routes/health.py`: health check endpoint
- `app/core/config.py`: environment-driven settings
- `app/db/connection.py`: DuckDB connection and bootstrap logic
- `app/schemas/health.py`: response schema
- `tests/test_health_check.py`: API smoke test
- `Dockerfile`: API image definition
- `docker-compose.yml`: local orchestration entrypoint
- `docs/duckdb-setup.md`: install, startup, and verification notes
- `docs/docker-setup.md`: Docker and compose setup notes
- `skills.md`: AI development guide for this repo

## Next Suggested Backend Steps

1. Add `system`, `documents`, and `query` routers.
2. Add DuckDB connection management.
3. Add ingestion and query DTOs.
4. Add service and repository layers from the architecture docs.
