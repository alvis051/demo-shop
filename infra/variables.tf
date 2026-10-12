variable "project_id" {
  description = "Google Cloud project that hosts both environments."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run and Artifact Registry. Keep it near the Neon region (us-west1 is next to Neon's aws-us-west-2)."
  type        = string
  default     = "us-west1"
}

variable "github_repository" {
  description = "owner/repo allowed to deploy through Workload Identity Federation."
  type        = string
  default     = "alvis051/demo-shop"
}

variable "admin_email" {
  description = "Admin account the seed creates in every environment. Its password is in Secret Manager."
  type        = string
  default     = "admin@example.com"
}
