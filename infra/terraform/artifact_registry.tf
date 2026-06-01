# Docker registry for the application images (api/worker share one image, web another).
resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "ledgercopilot"
  description   = "LedgerCopilot container images"
  format        = "DOCKER"

  # Keep storage bounded: drop everything but the most recent untagged digests.
  cleanup_policies {
    id     = "keep-recent-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s" # 7 days
    }
  }

  depends_on = [google_project_service.enabled]
}
