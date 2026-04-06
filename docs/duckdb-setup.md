# DuckDB Setup

This backend uses DuckDB as an embedded database inside the FastAPI process.

## Installation

DuckDB is installed through the backend Python dependencies:

```text
personal_records_intelligence_api/requirements.txt
```

Current package:

- `duckdb>=1.0,<2.0`

## Runtime Configuration

DuckDB is configured with the `DUCKDB_PATH` environment variable.

Default Docker path:

```text
/app/data/duckdb/app.duckdb
```

In this workspace, Docker Compose mounts that path to:

```text
./data/duckdb/app.duckdb
```

## Startup Behavior

On FastAPI startup:

1. the backend creates the DuckDB parent directory if needed
2. the backend opens a DuckDB connection
3. the backend bootstraps a minimal schema
4. the backend stores the connection manager on `app.state`

Bootstrap today creates:

- `app_metadata`

Seeded metadata today:

- `bootstrap_status = ready`
- `schema_version = 1`

## Where The Code Lives

- `app/core/config.py`: reads `DUCKDB_PATH`
- `app/db/connection.py`: opens DuckDB and bootstraps schema
- `app/main.py`: initializes DuckDB during app lifespan
- `app/api/routes/health.py`: exposes DuckDB status through `GET /health_check`
- `../Dockerfile`: builds the API container that installs the DuckDB dependency

## How To Run

From inside the API repo:

```bash
docker compose up --build -d
```

## How To Verify

### Check container status

```bash
docker compose ps
```

### Check API health

```bash
curl http://localhost:8000/health_check
```

Expected response shape:

```json
{
  "status": "ok",
  "database": {
    "status": "ok",
    "engine": "duckdb",
    "path": "/app/data/duckdb/app.duckdb"
  }
}
```

### Inspect bootstrap metadata

```bash
docker compose exec -T api python -c "import duckdb; con = duckdb.connect('/app/data/duckdb/app.duckdb'); print(con.execute('SELECT key, value FROM app_metadata ORDER BY key').fetchall())"
```

## Current Limitations

- one API process should own DuckDB writes
- current bootstrap only creates a metadata table
- schema migrations are not implemented yet

## Next Suggested Step

Add a repository layer and first real domain tables:

- `documents`
- `chunks`
- `query_runs`
