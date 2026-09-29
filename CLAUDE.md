# CLAUDE.md

This repo is `demo-shop`, the first target app for Blue Mage (`~/bluemage`). The plan
is `~/wiki/plans/grand-plan.md`, §2.

## Rules

- **Never write tests.** Nothing under `tests/` (specs, fixtures, helpers, page
  objects, `seed.spec.ts`) is written by a human or by a Claude session working on
  this repo. Tests only arrive through Blue Mage's PRs.
- **No Bestiary here.** Seeded regressions are written in a separate session that
  never sees Blue Mage's generator, and stored outside this repo. Don't add bug
  patches, regression lists or hints about them to this repo.
- **Markup like a real app.** Semantic HTML with roles and labels; **no
  `data-testid`** or other test-only hooks.
- **Keep it small** (roughly 1–2k lines): FastAPI, server-rendered pages, a fresh DB
  per process so a test run can start it hermetically on a random port.
- Fault knobs (bug flag, flaky endpoint, extra latency) are set by env var or an admin
  route and are off by default.
