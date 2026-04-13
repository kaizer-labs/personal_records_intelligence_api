# Backend Skills

This file is the quick-start context for AI-assisted development in this backend repository.

## Purpose

Build a trustworthy local-first API for document ingestion, retrieval, fact extraction, and deterministic answer generation.

## Read These First

1. `README.md`
2. `docs/api-contract.md`
3. `docs/development-workflow.md`
4. `docs/architecture.md`
5. `docs/low-level-architecture.md`

## Current Constraints

- single-user MVP
- local-first architecture
- FastAPI backend
- DuckDB embedded in the backend process
- Docker-based local development
- health endpoint exists at `GET /health_check`
- frontend lives in a separate sibling folder and connects over HTTP

## Coding Rules

- keep route handlers thin
- put validation in schemas and config modules
- put business logic in services, not routers
- use explicit response models
- prefer additive changes over broad refactors
- update markdown docs when architecture or contracts change

## File Ownership Guidance

- `app/api/`: HTTP layer only
- `app/core/`: shared config and application wiring
- `app/deps.py`: dependency wiring for routes and request-time services
- `app/repositories/`: persistence and SQL logic
- `app/schemas/`: request and response contracts
- `app/services/`: orchestration, AI logic, and file processing
- `tests/`: smoke tests and API contract tests
- `docs/`: human and AI onboarding context

## Done Checklist

- endpoint shape is documented
- response schemas stay explicit
- Docker startup still works
- markdown docs reflect the change
- syntax or tests were run when possible
