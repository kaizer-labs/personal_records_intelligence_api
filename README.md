# Personal Records Intelligence API

FastAPI backend for the Personal Records Intelligence MVP.

## Demo

Lightweight product preview:

![Personal Records Intelligence demo](docs/assets/demo/personal_records_intelligence_demo_light.gif)

## What This Repo Runs

- FastAPI backend on `http://localhost:8000`
- DuckDB as embedded local storage
- Docker orchestration for the backend plus sibling React UI
- Ollama integration for local chat and embeddings

## Prerequisites

Before starting the stack, make sure:

- Docker Desktop is running
- Ollama is installed and running on the Mac host
- the required models are available in Ollama

Check models:

```bash
ollama list
```

If needed, pull them:

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

## Local Model Defaults

- chat model: `qwen2.5:7b`
- embedding model: `nomic-embed-text`
- Ollama base URL from Docker: `http://host.docker.internal:11434`
- recommended chat context on this Mac: `4096`

## Setup

From inside this repo:

```bash
cd /Users/kaizer/Desktop/personal_records_intelligence/personal_records_intelligence_api
docker compose up --build
```

### Open The App

- UI: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- API health check: `http://localhost:8000/health_check`

### Verify The Backend

The health check should report:

- `status: ok`
- DuckDB path under `/app/data/duckdb/app.duckdb`
- Ollama chat model `qwen2.5:7b`
- Ollama embedding model `nomic-embed-text`

## Local Data And Privacy

- Indexed files and DuckDB data live under `data/`
- `data/` is gitignored and should remain local-only
- The `examples/` folder is for local demo/sample documents and is also ignored by git, except for `examples/README.md`

To reset local indexed data, stop the API container and clear `data/`.

## What Exists Today

- `GET /health_check`
- document ingestion and local example loading
- local chat over indexed records
- source-backed evidence inspection
- DuckDB startup initialization
- Ollama configuration for local generation and embeddings
- OpenAPI docs at `/docs`
- `docker-compose.yml` for API-local orchestration of backend plus sibling UI
- AI-friendly repository markdown files for onboarding and safe iteration

## Key Endpoints

- `GET /health_check`
- `GET /docs`
- `POST /api/library/examples/sync`
- `POST /api/library/folders/sync`
- `GET /api/library/folders`
- `POST /api/chat/answers`
- `POST /api/chat/answers/stream`

## Docs

- `docs/architecture.md`
- `docs/low-level-architecture.md`
- `docs/duckdb-setup.md`
- `docs/docker-setup.md`
- `docs/api-contract.md`
- `docs/development-workflow.md`

## Project Layout

- `app/main.py`: FastAPI app factory and startup wiring
- `app/api/routes/health.py`: health check endpoint
- `app/api/routes/library.py`: document and folder ingestion routes
- `app/api/routes/chat.py`: chat and streaming routes
- `app/core/config.py`: environment-driven settings
- `app/db/connection.py`: DuckDB connection and bootstrap logic
- `app/services/library.py`: library ingestion and file management
- `app/services/chat.py`: retrieval and answer orchestration
- `app/services/ollama.py`: local model client
- `Dockerfile`: API image definition
- `docker-compose.yml`: local orchestration entrypoint
- `skills.md`: AI development guide for this repo

## Next Suggested Backend Steps

1. Improve structured extraction for financial and admin records.
2. Add OCR support for scanned PDFs and image-heavy files.
3. Add stronger evaluation and citation confidence workflows.
4. Expand beyond documents into bookmarks and screenshots.
