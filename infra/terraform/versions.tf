# Terraform + provider pinning and remote state.
#
# State lives in a GCS bucket (remote + locked — never local, never committed;
# best practice). Bootstrap the bucket once, then:
#   terraform init -backend-config="bucket=<TF_STATE_BUCKET>"
# See README.md for the one-time bootstrap.

terraform {
  required_version = ">= 1.7"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.12"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.12"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "gcs" {
    prefix = "ledgercopilot/prod"
    # bucket supplied at init time via -backend-config (kept out of VCS).
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
