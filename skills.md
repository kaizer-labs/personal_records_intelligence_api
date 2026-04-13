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
- start every non-trivial task by writing test scenarios first
- prefer failing tests before implementation changes
- implement the smallest code change that satisfies the test contract
- prefer additive changes over broad refactors
- update markdown docs when architecture or contracts change

## Test-First Skill

Use this workflow as the default for backend tasks:

1. Write 3-5 scenario bullets before touching implementation.
2. Cover at least:
   - the primary success path
   - one edge case
   - one failure or regression case
3. Turn those scenarios into tests or update existing tests first.
4. Implement from the tests backward into the function, service, repository, or endpoint.
5. Refactor only after the new tests pass.

Short scenario template:

- `Given` the current state
- `When` the action happens
- `Then` the observable behavior matches the contract

If the code is hard to test, treat that as a design signal:

- extract a smaller unit
- move persistence behind a repository seam
- split orchestration from pure logic
- add fakes or fixtures instead of widening production code just for tests

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

- test scenarios were written before implementation
- failing tests were added or updated before code changes when feasible
- endpoint shape is documented
- response schemas stay explicit
- Docker startup still works
- markdown docs reflect the change
- syntax or tests were run when possible

Reusable workflow reference:

- `ai/skills/test-first-development.md`
