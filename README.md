# Personal Records Intelligence API

FastAPI backend for the Personal Records Intelligence MVP.

## Setup

Run the API service locally:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Or build and run the API container directly:

```bash
docker build -t personal-records-intelligence-api .
docker run --rm -p 8000:8000 personal-records-intelligence-api
```

Then open:

- `http://localhost:8000/health_check`
- `http://localhost:8000/docs`

## What Exists Today

- `GET /health_check`
- embedded DuckDB setup with startup initialization
- OpenAPI docs at `/docs`
- Dockerfile for local containerized development
- AI-friendly repository markdown files for onboarding and safe iteration

## Project Layout

- `app/main.py`: FastAPI app factory and middleware
- `app/api/routes/health.py`: health check endpoint
- `app/core/config.py`: environment-driven settings
- `app/db/connection.py`: DuckDB connection and bootstrap logic
- `app/schemas/health.py`: response schema
- `tests/test_health_check.py`: API smoke test
- `Dockerfile`: API image definition
- `skills.md`: AI development guide for this repo

## Next Suggested Backend Steps

1. Add `system`, `documents`, and `query` routers.
2. Add DuckDB connection management.
3. Add ingestion and query DTOs.
4. Add service and repository layers from the architecture docs.
