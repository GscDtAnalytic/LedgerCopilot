# Document storage — the bronze layer (raw uploaded bytes), persisted in GCS by
# packages/storage/gcs.py. Object versioning enforces bronze immutability at the
# storage layer; uniform access + public-access-prevention keep it private.

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "documents" {
  name     = "ledgercopilot-documents-${random_id.bucket_suffix.hex}"
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  # Bronze is immutable but not infinite — expire noncurrent versions after 1y.
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 365
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.enabled]
}
