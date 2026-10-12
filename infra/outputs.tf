output "image" {
  description = "Where CI pushes images."
  value       = local.image
}

output "urls" {
  description = "Each environment's URL."
  value       = { for env, service in google_cloud_run_v2_service.app : env => service.uri }
}

output "github_variables" {
  description = "Repository variables the workflows read. Set them with: gh variable set NAME --body VALUE"
  value = {
    GCP_PROJECT      = var.project_id
    GCP_REGION       = var.region
    GCP_WIF_PROVIDER = google_iam_workload_identity_pool_provider.github.name
  }
}
