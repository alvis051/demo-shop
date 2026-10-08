# demo-shop

A small online shop that exists to be tested by
[Blue Mage](https://github.com/alvis051/bluemage), an AI agent that explores a
running web app and writes its Playwright end-to-end tests.

It plays the part of a customer's app: login, catalog, cart, coupons, a fake
checkout (success / declined / retryable) and order history, built with FastAPI
and server-rendered pages.

## Running it locally

You need Python 3.13, [uv](https://docs.astral.sh/uv/) and a Postgres 16 database.

```sh
uv sync
export DATABASE_URL=postgresql://shop:shop@127.0.0.1:5432/shop
uv run python -m app            # prints "demo-shop listening on http://127.0.0.1:<port>"
```

By default (`DEMO_SHOP_ENV=test`) each process:

- creates its own schema (`run_<random>`) in that database, then migrates and seeds it
- listens on a random free port, printing the URL once it's ready
- drops its schema on exit

So a test run can start as many isolated copies as it likes against one database.
Use a direct connection, not a pooled one, because poolers drop the `search_path`
option. Pass `--port 8000` to pick a port.

Demo accounts: `alice@example.com` / `alice-pass`, `bob@example.com` / `bob-pass`
and `admin@example.com` / `admin-pass`.

### Test cards and coupons

| Card number | Result |
|---|---|
| 4242 4242 4242 4242 | Approved |
| 4000 0000 0000 0002 | Declined |
| 4000 0000 0000 0119 | Fails once with a temporary error, then succeeds on retry |

Any future expiry (MM/YY) and any 3-digit security code work with these cards.

Coupons: `SAVE10` (10% off), `FIVEOFF` ($5 off $25 or more), `EXPIRED` and
`WELCOME` (15% off, once per account).

### Fault knobs

These are all off by default and always off in prod. Set them with env vars, or
sign in as admin and use `/admin/faults`. `POST /admin/reset` restores the seed
data.

| Env var | Effect |
|---|---|
| `DEMO_SHOP_LATENCY_MS` | Extra delay on every request |
| `DEMO_SHOP_FLAKY_RATE` | Share (0–1) of checkout submissions that fail with 503; `DEMO_SHOP_FLAKY_SEED` makes it repeatable |
| `DEMO_SHOP_BUG` | A string nothing in this repo reads; available to patches applied from outside |

## Environments

| | daily | pre | prod |
|---|---|---|---|
| Deployed | every green CI run on `main` | `Deploy` workflow, `target=pre` | `Deploy` workflow, `target=prod`, after approval |
| Image | that commit's | a chosen `main` commit's | exactly what's on pre |
| Database | Neon branch `daily` | Neon branch `pre` | Neon branch `prod` (main) |
| Demo accounts and fault knobs | yes | yes | no |

- **Hosting:** each environment is a Render web service defined in `render.yaml`.
  It pulls `ghcr.io/alvis051/demo-shop:<env>`.
- **Releases:** CI builds the image once per commit. `.github/workflows/deploy.yml`
  points the environment's tag at that image and calls the service's Render
  deploy hook.
- **Migrations:** Render runs `alembic upgrade head && python -m app.seed` before
  switching traffic.
- **Version check:** `/healthz` returns `ok <git sha>`.

### One-time setup

1. Neon: create a project, and branches `daily`, `pre` and `ci` from the
   default branch. The default branch is prod.
2. Merge to `main` so CI pushes the first image and the `Deploy` workflow tags it
   `:daily`. Run `Deploy` with `target=pre` and then `target=prod` once, so all
   three tags exist. Until step 5 is done, these runs move the tags and skip the
   Render deploy.
3. Render: add a registry credential named `ghcr` (a GitHub token with
   `read:packages`), then create a Blueprint from this repo. When asked, enter
   each environment's `DATABASE_URL` (its Neon branch), `ADMIN_EMAIL` and
   `ADMIN_PASSWORD`.
4. GitHub: create environments `daily`, `pre` and `prod`. Give `prod` required
   reviewers.
5. In each GitHub environment, add the secret `RENDER_DEPLOY_HOOK` (from the
   service's settings in Render). Optionally add the variable `APP_URL`, so the
   deploy waits until the new version is serving.

## No hand-written tests

There is no `tests/` directory, on purpose. Every test in this repo is written by
Blue Mage and arrives through a pull request from its bot; CI rejects any change to
`tests/` authored by anyone else.

Blue Mage measures those tests by how many seeded regressions they catch. The
regressions (the Bestiary) live outside this repo, so no generator can read them.
