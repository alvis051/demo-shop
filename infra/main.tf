# demo-shop on Google Cloud: three Cloud Run services (daily, pre, prod), each with a
# migration job, runtime secrets and its own deployer identity for GitHub Actions.
# The database is Neon (one branch per environment), outside Google Cloud.
#
# Terraform owns the shape of each service. The Deploy workflow only changes the image,
# so Terraform ignores image changes.

terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.6"
    }
  }
  # The bucket is passed at init: terraform init -backend-config="bucket=<project>-tfstate"
  backend "gcs" {
    prefix = "demo-shop"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  envs  = toset(["daily", "pre", "prod"])
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/demo-shop"
  # Env var -> secret name. Each environment gets its own copy, e.g. demo-shop-pre-database-url.
  secret_env = { DATABASE_URL = "database-url", SESSION_SECRET = "session-secret", ADMIN_PASSWORD = "admin-password" }
  env_secrets = { for pair in setproduct(local.envs, values(local.secret_env)) : "${pair[0]}-${pair[1]}" => {
    env  = pair[0]
    name = pair[1]
  } }
  # Placeholder until the first deploy. The workflow replaces it; Terraform ignores the change.
  bootstrap_image = "us-docker.pkg.dev/cloudrun/container/hello"
  github_subject  = "principal://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/subject/repo:${var.github_repository}"
}

resource "google_project_service" "apis" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sts.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# --- Images ---------------------------------------------------------------------

resource "google_artifact_registry_repository" "images" {
  repository_id = "demo-shop"
  location      = var.region
  format        = "DOCKER"

  # Stay inside the free 0.5 GB: keep what each environment runs and the 10 newest builds.
  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "keep-environments"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["daily", "pre", "prod"]
    }
  }
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "604800s" # 7 days
    }
  }

  depends_on = [google_project_service.apis]
}

# --- GitHub Actions identity (OIDC, no keys) ----------------------------------------

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "demo-shop"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == '${var.github_repository}'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# CI pushes images from main only.
resource "google_service_account" "image_pusher" {
  account_id   = "image-pusher"
  display_name = "GitHub Actions: push demo-shop images from main"
}

resource "google_service_account_iam_member" "image_pusher_github" {
  service_account_id = google_service_account.image_pusher.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "${local.github_subject}:ref:refs/heads/main"
}

resource "google_artifact_registry_repository_iam_member" "image_pusher" {
  repository = google_artifact_registry_repository.images.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.image_pusher.member
}

# One deployer per environment, usable only by a job running in the matching GitHub
# Environment. prod's needs its required reviewers' approval first.
resource "google_service_account" "deployer" {
  for_each     = local.envs
  account_id   = "deploy-${each.key}"
  display_name = "GitHub Actions: deploy demo-shop ${each.key}"
}

resource "google_service_account_iam_member" "deployer_github" {
  for_each           = local.envs
  service_account_id = google_service_account.deployer[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "${local.github_subject}:environment:${each.key}"
}

# Moves the environment's tag (and reads :pre when promoting to prod).
resource "google_artifact_registry_repository_iam_member" "deployer" {
  for_each   = local.envs
  repository = google_artifact_registry_repository.images.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deployer[each.key].member
}

resource "google_cloud_run_v2_service_iam_member" "deployer" {
  for_each = local.envs
  name     = google_cloud_run_v2_service.app[each.key].name
  location = var.region
  role     = "roles/run.developer"
  member   = google_service_account.deployer[each.key].member
}

resource "google_cloud_run_v2_job_iam_member" "deployer" {
  for_each = local.envs
  name     = google_cloud_run_v2_job.migrate[each.key].name
  location = var.region
  role     = "roles/run.developer"
  member   = google_service_account.deployer[each.key].member
}

# Deploying a revision that runs as the runtime account needs actAs on it.
resource "google_service_account_iam_member" "deployer_acts_as_runtime" {
  for_each           = local.envs
  service_account_id = google_service_account.runtime[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer[each.key].member
}

# --- Runtime --------------------------------------------------------------------

resource "google_service_account" "runtime" {
  for_each     = local.envs
  account_id   = "demo-shop-${each.key}"
  display_name = "demo-shop ${each.key} runtime"
}

# Values are added by hand (see README), so they never pass through Terraform state.
resource "google_secret_manager_secret" "app" {
  for_each  = local.env_secrets
  secret_id = "demo-shop-${each.key}"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each  = local.env_secrets
  secret_id = google_secret_manager_secret.app[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runtime[each.value.env].member
}

resource "google_cloud_run_v2_service" "app" {
  for_each            = local.envs
  name                = "demo-shop-${each.key}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = each.key == "prod"

  template {
    service_account = google_service_account.runtime[each.key].email
    # One instance at most: fault knobs set through /admin/faults live in memory.
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    containers {
      image = local.bootstrap_image
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }
      env {
        name  = "DEMO_SHOP_ENV"
        value = each.key
      }
      env {
        name  = "ADMIN_EMAIL"
        value = var.admin_email
      }
      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["${each.key}-${env.value}"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.runtime]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = local.envs
  name     = google_cloud_run_v2_service.app[each.key].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Runs before each deploy: migrate, then seed. Same identity and settings as the service.
resource "google_cloud_run_v2_job" "migrate" {
  for_each            = local.envs
  name                = "demo-shop-migrate-${each.key}"
  location            = var.region
  deletion_protection = each.key == "prod"

  template {
    template {
      service_account = google_service_account.runtime[each.key].email
      max_retries     = 0
      timeout         = "300s"
      containers {
        image   = local.bootstrap_image
        command = ["sh", "-c"]
        args    = ["alembic upgrade head && python -m app.seed"]
        env {
          name  = "DEMO_SHOP_ENV"
          value = each.key
        }
        env {
          name  = "ADMIN_EMAIL"
          value = var.admin_email
        }
        dynamic "env" {
          for_each = local.secret_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.app["${each.key}-${env.value}"].secret_id
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.runtime]
}
