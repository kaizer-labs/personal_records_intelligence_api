# AGENTS.md

Shared project guidance for human contributors and AI coding assistants working in this repository.

## Purpose

This repo is the backend API for a local-first Personal Records Intelligence product.

Current stack:

- FastAPI for HTTP APIs
- DuckDB for embedded persistence
- Ollama for local chat and embeddings
- Docker Compose for local startup with the sibling UI

## Start Here

Read these files in order before making non-trivial changes:

1. `README.md`
2. `docs/architecture.md`
3. `docs/api-contract.md`
4. `docs/development-workflow.md`
5. `docs/low-level-architecture.md`

## What Exists Today

The current implementation is an MVP with these concrete capabilities:

- health endpoint
- browser-uploaded document ingestion
- text extraction for PDF, TXT, Markdown, CSV, and JSON
- chunk storage and optional embeddings
- grounded chat answers with source excerpts
- DuckDB bootstrap and local artifact storage

The docs also describe a target architecture with facts, query traces, validators, and calculators. Treat that as the intended direction, not as functionality that already exists everywhere in code.

## Repo Map

- `app/main.py`: app factory and lifespan wiring
- `app/api/`: routers and HTTP layer
- `app/core/`: config and shared application concerns
- `app/deps.py`: reusable route dependency helpers
- `app/db/`: DuckDB bootstrap and access layer
- `app/repositories/`: persistence and SQL boundaries
- `app/schemas/`: request and response contracts
- `app/services/`: current business logic
- `docs/`: architecture, API, and workflow documentation
- `tests/`: smoke and contract tests

## Working Rules

- Keep route handlers thin and push logic down into dependencies, repositories, or services.
- Prefer explicit schemas and stable response shapes over ad hoc dicts.
- Update docs when contracts, architecture, startup flow, or package structure changes.
- Start each non-trivial task by writing down concrete test scenarios before changing code.
- Prefer test-first delivery: add or update failing tests, then work backward into the minimum implementation that satisfies them.
- When a change touches existing behavior, add characterization tests first so refactors are anchored to the current contract.
- Add tests with behavior changes whenever practical.
- Avoid growing already-large files if a new module boundary would make the change easier to understand.

## Test-First Workflow

For feature work, bug fixes, refactors, and AI-assisted changes, follow this sequence unless there is a strong reason not to:

1. Define the behavior in test scenarios before editing implementation code.
2. Cover the happy path, the primary edge case, and the most important failure mode.
3. Translate those scenarios into failing tests or update existing tests to express the new contract.
4. Implement the smallest code change that makes those tests pass.
5. Refactor only after the behavior is protected by tests.
6. Re-run the targeted tests first, then the broader repo checks that fit the change.

Preferred scenario format:

- `Given`: starting state or input
- `When`: action taken
- `Then`: expected observable result

If a task cannot start with tests, document why. Good reasons include third-party exploration spikes, temporary debugging, or infrastructure work with no stable seam yet. In those cases, add characterization or regression tests as soon as the seam becomes clear.

## Current Refactor Direction

As the backend grows, prefer moving toward this structure:

```text
root/
  AGENTS.md
  README.md
  docs/
  ai/
    skills/
    prompts/
  app/
    api/
      v1/
        endpoints/
        api.py
    core/
    db/
    repositories/
    schemas/
    services/
      ingestion/
      retrieval/
      answer/
      system/
    deps.py
    main.py
  tests/
```

Guidance behind that structure:

- `AGENTS.md` should be the canonical contributor entrypoint across tools.
- `api/v1` is worth adding once the public surface grows beyond bootstrap MVP endpoints.
- `endpoints/` is better than a large flat routes folder when the API surface expands.
- `repositories/` is a better fit than ORM-style `models/` for the current DuckDB-plus-SQL approach.
- `deps.py` should own reusable request-scoped dependencies such as database, services, and clients.
- `ai/skills/` and `ai/prompts/` are optional support folders and should never be required for app runtime.

## Risk Areas To Improve

These are the main maturity gaps to keep in mind while changing the repo:

- ingestion should not delete prior documents during partial uploads
- synchronous AI work should not block the async request path forever
- health endpoints should reflect dependency readiness, not just configuration
- embedding failures should be visible in status and tests
- auditability needs persisted traces, warnings, and fact-level data

## Verification

Use the lightest checks that fit the change:

- targeted `pytest` cases for the affected module or endpoint
- `env PYTHONPYCACHEPREFIX=/tmp/pri-pycache python3 -m compileall app tests`
- `pytest -q`
- `docker compose up --build`

If a verification step cannot run in the current environment, say so explicitly in the final handoff.

## Tool-Specific Rules

Tool-specific AI guidance is allowed, but keep it layered:

- project-wide truth belongs in `AGENTS.md`
- IDE-specific rules can live under `.cursor/rules/`
- reusable AI workflows can live under `ai/skills/`
- task-specific prompts can live under `ai/prompts/`

Those files should refine this guide, not contradict it.

Current reusable workflow:

- `ai/skills/test-first-development.md`: define scenarios first, write failing tests, then implement backward from the contract
