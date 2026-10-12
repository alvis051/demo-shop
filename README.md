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

| | staging | prod |
|---|---|---|
| Deployed | every green CI run on `main` | the same run, once a `prod` reviewer approves |
| Image | that commit's | the exact digest staging verified |
| Rollout | replaces the running revision | blue-green (below) |
| Database | Neon branch `staging` | Neon's default branch |
| Demo accounts and fault knobs | yes | no |

- **Hosting:** each environment is a Cloud Run service (`demo-shop-<env>`) on Google
  Cloud, scaling to zero, with at most one instance. Everything on Google Cloud is
  defined in Terraform under `infra/`. The database stays on Neon: Cloud SQL has no
  free tier, and Neon gives each environment its own branch.
- **Releases:** CI builds the image once per commit and pushes it to Artifact
  Registry. `.github/workflows/deploy.yml` deploys that digest to staging, checks
  `/health`, then waits for approval to promote the same digest to prod. The
  `:staging` and `:prod` tags mark what each environment has verified.
- **Blue-green on prod:** the new revision (green) starts with no traffic, tagged
  `candidate`, so it gets its own URL. It's smoke-tested there against prod's
  database, and only then takes all the traffic. If the smoke test fails, no user
  ever reached it.
- **Rollback:** the previous revision (blue) keeps running with no traffic. Each
  prod deploy's summary prints the `gcloud run services update-traffic` command
  that moves traffic back to it. To redeploy an older commit through the whole
  pipeline, run `Deploy` by hand with its SHA; this only works if no migration has
  landed since, otherwise roll forward.
- **Migrations:** the Cloud Run job `demo-shop-migrate-<env>` runs
  `alembic upgrade head && python -m app.seed` before traffic moves.
- **Secrets:** `DATABASE_URL`, `SESSION_SECRET` and `ADMIN_PASSWORD` come from
  Secret Manager (`demo-shop-<env>-<name>`). Their values never pass through
  Terraform or GitHub.
- **Access:** GitHub Actions signs in through Workload Identity Federation, with no
  stored keys. Only `main` can push images, and each environment's deployer can only
  be used from the matching GitHub Environment.
- **Version check:** `/health` returns `ok <git sha>`. (Not `/healthz`: Cloud Run
  reserves some paths ending in `z`.)

### One-time setup

You need `gcloud`, `terraform` and `gh`. Pick a project ID and a region near your
Neon region (the default, `us-west1`, is next to Neon's `aws-us-west-2`).

```sh
export PROJECT=<project-id> REGION=us-west1
```

1. Neon: create a project, and branches `staging` and `ci` from the default
   branch. The default branch is prod.
2. Google Cloud: create the project, link billing, and set a budget alert.

   ```sh
   gcloud projects create $PROJECT
   gcloud billing projects link $PROJECT --billing-account=<billing-account-id>
   gcloud billing budgets create --billing-account=<billing-account-id> \
     --display-name=demo-shop --budget-amount=5USD \
     --threshold-rule=percent=0.5 --threshold-rule=percent=1.0
   gcloud storage buckets create gs://$PROJECT-tfstate --project=$PROJECT \
     --location=$REGION --uniform-bucket-level-access
   gcloud storage buckets update gs://$PROJECT-tfstate --versioning
   ```

3. Terraform, part one: the APIs and the empty secrets. The services can't start
   until the secrets have values.

   ```sh
   cd infra
   terraform init -backend-config="bucket=$PROJECT-tfstate"
   terraform apply -var project_id=$PROJECT -var region=$REGION \
     -target=google_secret_manager_secret.app
   ```

4. Secret values, for each environment (`staging`, `prod`). `DATABASE_URL` is
   the connection string of that environment's Neon branch.

   ```sh
   env=staging
   printf %s '<neon connection string>' | gcloud secrets versions add demo-shop-$env-database-url --project=$PROJECT --data-file=-
   openssl rand -base64 32 | tr -d '\n' | gcloud secrets versions add demo-shop-$env-session-secret --project=$PROJECT --data-file=-
   printf %s '<admin password>' | gcloud secrets versions add demo-shop-$env-admin-password --project=$PROJECT --data-file=-
   ```

5. Terraform, part two: everything else.

   ```sh
   terraform apply -var project_id=$PROJECT -var region=$REGION
   ```

6. GitHub: create environments `staging` and `prod`, and give `prod` required
   reviewers. Then set the repository variables that `terraform output
   github_variables` prints (`GCP_PROJECT`, `GCP_REGION`, `GCP_WIF_PROVIDER`) with
   `gh variable set`. Until they're set, CI builds the image without pushing it and
   `Deploy` is skipped.
7. Merge to `main`. CI pushes the first image, and `Deploy` ships it to staging and
   then waits for your approval to ship it to prod.

A changed secret takes effect on the next deploy: Cloud Run reads `latest` when it
creates a revision. The same goes for a Terraform change to prod's service: it
creates a revision with no traffic, and the next deploy carries it live.

## No hand-written tests

There is no `tests/` directory, on purpose. Every test in this repo is written by
Blue Mage and arrives through a pull request from its bot; CI rejects any change to
`tests/` authored by anyone else.

Blue Mage measures those tests by how many seeded regressions they catch. The
regressions (the Bestiary) live outside this repo, so no generator can read them.
