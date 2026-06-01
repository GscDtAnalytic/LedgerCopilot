# Runtime service accounts — one per Cloud Run service, each scoped to the minimum
# it needs (least privilege;). DB access is over private
# IP + password, so no cloudsql.client role is granted.

resource "google_service_account" "run_api" {
  account_id   = "lc-run-api"
  display_name = "LedgerCopilot API (Cloud Run)"
}

resource "google_service_account" "run_worker" {
  account_id   = "lc-run-worker"
  display_name = "LedgerCopilot worker (Cloud Run)"
}

resource "google_service_account" "run_web" {
  account_id   = "lc-run-web"
  display_name = "LedgerCopilot web (Cloud Run)"
}

locals {
  # API and worker share the same backend privileges (secrets + document bucket).
  backend_sa_members = [
    "serviceAccount:${google_service_account.run_api.email}",
    "serviceAccount:${google_service_account.run_worker.email}",
  ]
  app_secrets = {
    secret_key   = google_secret_manager_secret.secret_key.secret_id
    database_url = google_secret_manager_secret.database_url.secret_id
    anthropic    = google_secret_manager_secret.anthropic_api_key.secret_id
  }
  # secret_id × member → flattened set for per-secret IAM bindings.
  secret_bindings = {
    for pair in setproduct(keys(local.app_secrets), local.backend_sa_members) :
    "${pair[0]}:${pair[1]}" => { secret = local.app_secrets[pair[0]], member = pair[1] }
  }
}

# Read access to each app secret for the backend SAs.
resource "google_secret_manager_secret_iam_member" "backend_secret_access" {
  for_each  = local.secret_bindings
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}

# Read/write the document bucket (put bronze bytes, read them back).
resource "google_storage_bucket_iam_member" "backend_bucket_access" {
  for_each = toset(local.backend_sa_members)
  bucket   = google_storage_bucket.documents.name
  role     = "roles/storage.objectAdmin"
  member   = each.value
}
