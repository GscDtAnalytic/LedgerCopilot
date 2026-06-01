output "api_url" {
  description = "Public URL of the API service."
  value       = google_cloud_run_v2_service.api.uri
}

output "web_url" {
  description = "Public URL of the web app."
  value       = google_cloud_run_v2_service.web.uri
}

output "artifact_registry" {
  description = "Docker repo path images are pushed to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}

output "documents_bucket" {
  value = google_storage_bucket.documents.name
}

# --- CI/CD wiring: paste these into GitHub repo secrets/variables -------------
output "workload_identity_provider" {
  description = "Set as GitHub variable GCP_WIF_PROVIDER (google-github-actions/auth)."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "Set as GitHub variable GCP_DEPLOYER_SA."
  value       = google_service_account.deployer.email
}

output "migrate_job_name" {
  value = google_cloud_run_v2_job.migrate.name
}

output "worker_service_name" {
  value = google_cloud_run_v2_service.worker.name
}
