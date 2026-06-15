# Development Guide

This project keeps checks lightweight because the deployed server is small and the current product scale is limited.

## Local Tooling

- Python projects use `uv`, `pytest`, and `ruff`.
- The web app uses `npm`, TypeScript, ESLint, Vite, and Prettier.
- Python runtime baseline: `3.12`. Docker and CI should stay aligned with this version.
- Recommended Node.js version for frontend development: `22.13+`.
- Release checklist: `docs/release-checklist.md`.
- Code style details: `docs/code-style.md`.
- Git/version change log: `docs/git-version-history.md`.

## Before Changing Code

- Work on `develop` unless a hotfix explicitly targets another branch.
- Keep feature changes scoped to the owning package.
- Do not commit local data, sqlite files, logs, `.env`, build output, or generated cache files.

## Python Checks

Run these inside each Python package when it is touched:

```bash
uv run ruff check src tests
uv run pytest
```

`ruff` also has formatting configured. Full format checking is intentionally not part of the default gate yet because
existing files have not been normalized in a dedicated formatting commit.

```bash
uv run ruff format src tests
uv run ruff format --check src tests
```

## Frontend Checks

Run these inside `interview-agent/web` when frontend files are touched:

```bash
npm run lint
npm run build
```

Prettier is available for frontend formatting:

```bash
npm run format
npm run format:check
```

## Whole-Project Check

From the repository root:

```bash
bash scripts/check.sh
```

Use an isolated uv cache only when the default user cache is not accessible:

```bash
ISOLATED_UV_CACHE=1 bash scripts/check.sh
```

Set `CHECK_FORMAT=1` only after running the dedicated formatter for the touched area:

```bash
CHECK_FORMAT=1 bash scripts/check.sh
```

## Review Focus

For this project, prioritize:

- user data leakage and account/session safety;
- public site hijack or unsafe reverse proxy behavior;
- server resource usage on a 2-core, 2GB machine;
- broken interview state, memory, RAG, or coding task flow;
- frontend build and TypeScript regressions.
