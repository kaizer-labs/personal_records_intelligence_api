# API Contract

## Current Endpoints

### `GET /health_check`

Returns service readiness metadata.

Example response:

```json
{
  "status": "ok",
  "service": "Personal Records Intelligence API",
  "version": "0.1.0",
  "environment": "development",
  "database": {
    "status": "ok",
    "engine": "duckdb",
    "version": "v1.x.x",
    "path": "/app/data/duckdb/app.duckdb",
    "table_count": 1
  }
}
```

## Near-Term Planned Endpoints

- `GET /`
- `GET /health_check`
- `GET /system/capabilities`
- `POST /ingestion/jobs`
- `GET /ingestion/jobs/{job_id}`
- `POST /query-runs`

## API Design Principles

- version routes once the surface expands beyond bootstrap endpoints
- keep health and readiness endpoints simple and dependency-light
- return structured payloads rather than plain strings
- prefer stable JSON keys over ad hoc response shapes
