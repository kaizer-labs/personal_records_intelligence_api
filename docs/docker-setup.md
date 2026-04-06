# Docker Setup

This project uses Docker Compose from inside the API repo to run the API and UI together during local development.

## Files Involved

- `../Dockerfile`: API image definition
- `../docker-compose.yml`: API-local service orchestration
- `../requirements.txt`: Python dependencies installed into the API image

## API Container Behavior

The API container:

1. builds from `python:3.11-slim`
2. installs backend dependencies from `requirements.txt`
3. mounts the API repo into `/app`
4. mounts `../data` into `/app/data`
5. runs `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`

## Dockerfile Summary

The API `Dockerfile`:

- sets `/app` as the working directory
- installs Python dependencies
- copies the API source tree into the image
- exposes port `8000`

## Compose Summary

The API-local `docker-compose.yml` defines:

- `api`: FastAPI backend on port `8000`
- `ui`: React frontend on port `5173` from the sibling UI repo

The API service also provides:

- `APP_NAME`
- `APP_VERSION`
- `APP_ENV`
- `CORS_ORIGINS`
- `DUCKDB_PATH`

## Run The Stack

From inside the API repo:

```bash
docker compose up --build
```

To run only the API:

```bash
docker compose up --build api
```

To stop the stack:

```bash
docker compose down
```

## Verify The API Container

```bash
docker compose ps
docker compose logs api --tail=100
curl http://localhost:8000/health_check
```

## DuckDB Persistence

DuckDB data is persisted through the API repo mount:

```text
../data/duckdb/app.duckdb
```

That path is mounted into the API container as:

```text
/app/data/duckdb/app.duckdb
```

## Notes

- Docker Compose now lives in the API repo even though it also orchestrates the sibling UI repo.
- The UI service is referenced through `../personal_records_intelligence_ui`.
