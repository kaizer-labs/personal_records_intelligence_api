# Development Workflow

## Why This Repo Is Markdown-Heavy

The backend is intended to be easy for both humans and AI agents to change safely. That means key assumptions, boundaries, and contracts should live in the repo rather than only in conversation history.

## Change Workflow

1. Read `skills.md` and the relevant docs before editing.
2. Keep route handlers focused on HTTP concerns.
3. Add or update schemas before widening API behavior.
4. Update repo markdown if you change contracts, architecture, or workflow.
5. Run a verification step before wrapping up.

## Verification Expectations

- syntax validation for Python modules
- API smoke tests when dependencies are available
- Docker boot verification when environment support exists

## Documentation Expectations

Update docs when you change:

- endpoint URLs or response shapes
- startup commands or Docker behavior
- folder structure conventions
- architecture assumptions

