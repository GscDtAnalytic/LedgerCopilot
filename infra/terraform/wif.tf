# Workload Identity Federation — keyless GitHub Actions → GCP auth. No long-lived
# JSON service-account key ever exists; GitHub's OIDC token is exchanged for a
# short-lived GCP token, restricted to this exact repository
# (prefer short-lived federated identity to static keys).

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions pool"
  depends_on                = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Only tokens minted for our repo can use this provider.
  attribute_condition = "assertion.repository == '${var.github_repo}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# The identity CI assumes to deploy.
resource "google_service_account" "deployer" {
  account_id   = "lc-github-deployer"
  display_name = "LedgerCopilot CI/CD deployer"
}

# Let workflows from our repo impersonate the deployer SA.
resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# Project-level roles the deployer needs to push images and roll out revisions.
resource "google_project_iam_member" "deployer_roles" {
  for_each = toset([
    "roles/run.admin",               # deploy services + run jobs (migrations)
    "roles/artifactregistry.writer", # push images
    "roles/serviceusage.serviceUsageConsumer",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Deploying a service means "acting as" its runtime SA — grant that narrowly on
# each runtime SA rather than project-wide.
resource "google_service_account_iam_member" "deployer_actas" {
  for_each = {
    api    = google_service_account.run_api.name
    worker = google_service_account.run_worker.name
    web    = google_service_account.run_web.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
