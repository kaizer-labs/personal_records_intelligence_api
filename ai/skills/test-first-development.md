# Test-First Development Skill

Use this skill when implementing or modifying backend behavior in this repository.

## Goal

Make changes from the contract backward:

1. define behavior as scenarios
2. encode those scenarios in tests
3. implement the smallest code change that makes the tests pass
4. refactor only after behavior is protected

## Default Workflow

1. Read `AGENTS.md`, `skills.md`, and the relevant architecture or API docs.
2. Write 3-5 scenario bullets before opening production files.
3. Convert the scenarios into tests or update existing tests first.
4. Run the new tests and confirm they fail for the expected reason.
5. Implement the minimum code necessary.
6. Re-run the targeted tests.
7. Run broader verification only after the focused tests pass.

## Scenario Template

- `Given` the state, input, or fixture setup
- `When` the action is taken
- `Then` the observable contract is satisfied

Example:

- `Given` a stored document and a browser upload batch with one replacement file
- `When` folder sync runs
- `Then` the updated document is re-indexed and unrelated stored documents are not deleted

## Minimum Coverage for a Task

Unless the task is truly tiny, define scenarios for:

- the primary success path
- the most likely edge case
- the most important failure or regression path

## Mapping Scenarios to Test Types

- pure logic: unit tests first
- service orchestration: fake-based service tests
- repositories: temporary DuckDB tests
- HTTP behavior: endpoint tests through FastAPI `TestClient`
- refactors: characterization tests before restructuring code

## If Testing Feels Hard

Treat that as a design signal instead of skipping tests.

Prefer:

- extracting a pure helper
- moving SQL behind a repository boundary
- splitting orchestration from I/O
- injecting a fakeable dependency

Avoid:

- widening implementation first and promising to test later
- hiding side effects inside route handlers
- coupling business rules directly to HTTP request parsing

## Completion Standard

Before closing a task, confirm:

- scenarios were written first
- tests capture the intended contract
- implementation changed only after the tests existed
- targeted tests pass
- broader verification was run when appropriate
