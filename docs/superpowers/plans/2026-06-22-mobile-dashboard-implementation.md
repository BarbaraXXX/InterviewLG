# Mobile Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved app-style mobile Dashboard and global bottom navigation without changing desktop behavior or backend contracts.

**Architecture:** Keep `App` as the view state owner, extract mobile navigation visibility and active-item rules into a pure TypeScript module, and render a focused `MobileBottomNav` component for authenticated non-chat views. Render a separate mobile Dashboard presentation from the same session data while retaining the existing desktop Dashboard markup.

**Tech Stack:** React 19, TypeScript 6, Vite 8, CSS media/container queries, Node built-in test runner, lucide-react.

---

### Task 1: Mobile navigation rules

**Files:**
- Create: `interview-agent/web/src/mobileNavigation.ts`
- Create: `interview-agent/web/src/mobileNavigation.test.ts`
- Modify: `interview-agent/web/package.json`

- [x] Write Node tests proving navigation is visible only for dashboard/setup/profile/history/insights and maps dashboard/setup/history/profile to the correct active item.
- [x] Run `node --test src/mobileNavigation.test.ts` and verify it fails because the module does not exist.
- [x] Implement typed visibility and active-item helpers.
- [x] Run the test again and verify it passes.

### Task 2: Bottom navigation component

**Files:**
- Create: `interview-agent/web/src/MobileBottomNav.tsx`
- Modify: `interview-agent/web/src/App.tsx`
- Modify: `interview-agent/web/src/index.css`
- Modify: `interview-agent/web/package.json`
- Modify: `interview-agent/web/package-lock.json`

- [x] Add `lucide-react` for Home, PlusCircle, History, and UserRound icons.
- [x] Render the navigation from `App` only for the approved views and connect each item to existing view transitions.
- [x] Add mobile-only fixed navigation styles, safe-area handling, 44px touch targets, active/focus states, and desktop hiding.
- [x] Keep the legal footer in normal document flow when mobile navigation is present to prevent overlap.

### Task 3: Mobile Dashboard presentation

**Files:**
- Modify: `interview-agent/web/src/App.tsx`
- Modify: `interview-agent/web/src/index.css`

- [x] Keep the current Dashboard grid as the desktop presentation.
- [x] Add a mobile presentation containing latest-session context, one primary start action, compact training metrics, resume/insights shortcuts, interrupted-session shortcut, and expandable release notes.
- [x] Switch presentations using CSS viewport rules and use component-sized responsive grids for narrow content.
- [x] Verify empty and failed summary states remain usable.

### Task 4: Documentation and verification

**Files:**
- Modify: `docs/git-version-history.md`

- [x] Record the implemented mobile Dashboard and bottom navigation under `Unreleased`.
- [x] Run `npm test`, `npm run lint`, `npm run build`, and `git diff --check`.
- [ ] Inspect 320, 390, 430, 768, and 1280 CSS-pixel layouts, navigation visibility, horizontal overflow, and desktop regression. Browser automation is blocked in the current runtime; complete this check in the user's local browser after implementation.
- [x] Commit only implementation, tests, plan/spec, and version history; do not commit `.superpowers/` visual artifacts.
