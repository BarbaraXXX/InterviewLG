# Admin Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent admin login and lightweight monitoring dashboard for online users and usage counters.

**Architecture:** Reuse the existing FastAPI, SQLite, and React/Vite deployment, but keep admin identity and routes separate from normal user identity. Store only low-sensitivity presence and daily aggregate metrics, then expose admin-only APIs and a `/admin` frontend shell.

**Tech Stack:** FastAPI, PyJWT, bcrypt, aiosqlite, pytest, React, TypeScript, Vite, existing CSS system.

---

## File Structure

- Modify `interview-agent/src/interview_agent/config.py`: add admin auth settings.
- Create `interview-agent/src/interview_agent/admin_auth.py`: admin password hashing, JWT, cookie auth dependency.
- Modify `interview-agent/src/interview_agent/db.py`: add admin, presence, usage tables and query helpers.
- Create `interview-agent/src/interview_agent/admin_cli.py`: command-line admin user creation.
- Modify `interview-agent/pyproject.toml`: add `interview-agent-admin` script.
- Modify `interview-agent/src/interview_agent/server.py`: add admin auth routes, heartbeat route, admin metrics routes, and usage counter calls.
- Modify `interview-agent/web/src/api.ts`: add admin auth, metrics, presence, and heartbeat client functions.
- Modify `interview-agent/web/src/App.tsx`: route `/admin/login` and `/admin` to an isolated admin shell; add regular-user heartbeat.
- Modify `interview-agent/web/src/index.css`: style admin login and admin monitoring pages.
- Add or modify tests in `interview-agent/tests/test_admin_monitoring.py` and `interview-agent/web/src/adminNavigation.test.ts`.

## Task 1: Backend Admin Auth

- [x] Add failing pytest coverage for admin auth helpers and admin-only API access.
- [x] Implement `AdminAuthSettings`, `admin_auth.py`, `admin_users` table helpers, and CLI user creation.
- [x] Add `/api/admin/auth/login`, `/api/admin/auth/logout`, and `/api/admin/auth/me`.
- [x] Verify ordinary user auth cannot satisfy admin auth.

## Task 2: Presence And Usage Metrics

- [x] Add failing pytest coverage for `user_presence` upsert/list and `daily_usage_stats` increment/range queries.
- [x] Implement DB tables and helpers.
- [x] Add `/api/presence/heartbeat` for authenticated normal users.
- [x] Add usage counter calls for login success, session creation, chat turn, speech transcription, coding submit, session completed, and session paused.

## Task 3: Admin Monitoring API

- [x] Add failing pytest coverage for admin-only overview, presence, and daily usage endpoints.
- [x] Implement `/api/admin/metrics/overview`, `/api/admin/presence`, and `/api/admin/usage/daily`.
- [x] Enforce safe limits: online window 5 minutes, recent window 15 minutes, daily usage `days` clamped to 1-30.
- [x] Ensure returned data excludes message bodies, resume bodies, code bodies, audio text, cookies, and password hashes.

## Task 4: Admin Frontend Shell

- [x] Add frontend tests for route classification helpers if helpers are extracted.
- [x] Implement `/admin/login` and `/admin` rendering based on `window.location.pathname`.
- [x] Add admin API calls and isolated admin auth state.
- [x] Add normal-user heartbeat with low frequency and visibility-aware behavior.
- [x] Style admin login and monitoring dashboard with existing product visual language.

## Task 5: Verification And Documentation

- [x] Run focused backend tests for admin monitoring.
- [x] Run full backend tests or the project check script if feasible.
- [x] Run frontend test, lint, and build.
- [x] Update `docs/git-version-history.md` with implementation notes.
- [x] Commit implementation on `develop`.
