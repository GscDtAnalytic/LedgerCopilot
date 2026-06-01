variable "project_id" {
  type        = string
  description = "GCP project ID hosting LedgerCopilot production."
}

variable "region" {
  type        = string
  description = "Primary region for all regional resources (Cloud Run, Cloud SQL, Memorystore, Artifact Registry)."
  default     = "southamerica-east1" # São Paulo — keeps financial document data in Brazil (LGPD residency).
}

variable "github_repo" {
  type        = string
  description = "owner/repo allowed to deploy via Workload Identity Federation (keyless CI auth)."
  default     = "GscDtAnalytic/LedgerCopilot"
}

variable "bootstrap_image" {
  type        = string
  description = <<-EOT
    Placeholder image used the first time Terraform creates the Cloud Run services
    and job. CI/CD owns the real image rollout thereafter (Terraform ignores image
    drift), so this only needs to be a public image that serves HTTP on $PORT.
  EOT
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "db_tier" {
  type        = string
  description = "Cloud SQL machine tier."
  default     = "db-g1-small"
}

variable "redis_memory_gb" {
  type        = number
  description = "Memorystore (Redis) capacity in GB."
  default     = 1
}

variable "ai_default_model" {
  type        = string
  description = "Default model for the AI gateway."
  default     = "claude-opus-4-8"
}

variable "ai_fallback_model" {
  type        = string
  description = "Fallback model for the AI gateway."
  default     = "claude-sonnet-4-6"
}

variable "api_min_instances" {
  type        = number
  description = "Minimum warm API instances (0 = scale to zero)."
  default     = 0
}

variable "api_max_instances" {
  type    = number
  default = 10
}

variable "web_max_instances" {
  type    = number
  default = 5
}
