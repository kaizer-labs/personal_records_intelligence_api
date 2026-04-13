# Development Workflow

## Why This Repo Is Markdown-Heavy

The backend is intended to be easy for both humans and AI agents to change safely. That means key assumptions, boundaries, and contracts should live in the repo rather than only in conversation history.

## Change Workflow

1. Read `skills.md` and the relevant docs before editing.
2. Define the expected behavior as concrete test scenarios before touching implementation code.
3. Add or update the failing tests that express those scenarios.
4. Keep route handlers focused on HTTP concerns.
5. Add or update schemas before widening API behavior.
6. Implement the smallest code change that makes the tests pass.
7. Update repo markdown if you change contracts, architecture, or workflow.
8. Run a verification step before wrapping up.

Recommended scenario structure:

- `Given` the relevant starting state
- `When` the behavior is triggered
- `Then` the result is observable through a response, return value, stored record, or emitted event

Minimum scenario set for most tasks:

- happy path
- meaningful edge case
- failure or regression case

## Verification Expectations

- targeted tests for the affected module first
- syntax validation for Python modules
- API smoke tests when dependencies are available
- Docker boot verification when environment support exists

## Documentation Expectations

Update docs when you change:

- endpoint URLs or response shapes
- startup commands or Docker behavior
- folder structure conventions
- architecture assumptions
