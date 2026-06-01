# Cloud Run services (api, web, worker) + the migration job.
#
# Division of ownership: Terraform owns the service *shape* (SA, scaling, network,
# env, secrets). CI/CD owns the *image* (and the worker/job start command), so each
# of those has `ignore_changes` — Terraform won't revert a `gcloud run deploy` and
# CI won't fight Terraform (infra as code + image rollout in
# the pipeline). First `apply` uses var.bootstrap_image just to create the resource.

locals {
  # Non-secret backend config shared by API, worker and the migration job.
  backend_env = {
    ENVIRONMENT           = "production"
    LOG_LEVEL             = "INFO"
    STORAGE_BACKEND       = "gcs"
    STORAGE_GCS_BUCKET    = google_storage_bucket.documents.name
    REDIS_URL             = local.redis_url
    AI_GATEWAY_PROVIDER   = "anthropic"
    AI_DEFAULT_MODEL      = var.ai_default_model
    AI_FALLBACK_MODEL     = var.ai_fallback_model
    HITL_TEMPORAL_ENABLED = "false" # no Temporal server in prod MVP; pipeline degrades gracefully
  }

  # name → secret_id, injected as env from Secret Manager (latest version).
  backend_secret_env = {
    DATABASE_URL      = google_secret_manager_secret.database_url.secret_id
    SECRET_KEY        = google_secret_manager_secret.secret_key.secret_id
    ANTHROPIC_API_KEY = google_secret_manager_secret.anthropic_api_key.secret_id
  }

  # The API also needs the browser-facing CORS origin = the deployed web URL.
  api_env = merge(local.backend_env, {
    CORS_ALLOW_ORIGINS = jsonencode([google_cloud_run_v2_service.web.uri])
  })

  backend_depends_on = [
    google_vpc_access_connector.connector,
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.secret_key,
    google_secret_manager_secret_iam_member.backend_secret_access,
  ]
}

# ── API ──────────────────────────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "api" {
  name                = "ledgercopilot-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.run_api.email

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = var.api_max_instances
    }

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.bootstrap_image
      ports {
        container_port = 8080
      }

      dynamic "env" {
        for_each = local.api_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.backend_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 10
        period_seconds        = 5
        failure_threshold     = 6
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [
    google_project_service.enabled,
    google_vpc_access_connector.connector,
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.secret_key,
    google_secret_manager_secret_iam_member.backend_secret_access,
  ]
}

# ── Worker (arq) — always-on, CPU never throttled ────────────────────────────
resource "google_cloud_run_v2_service" "worker" {
  name                = "ledgercopilot-worker"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false

  template {
    service_account = google_service_account.run_worker.email

    scaling {
      min_instance_count = 1 # keep one consumer warm draining the queue
      max_instance_count = 2
    }

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.bootstrap_image
      # command/args set by CI: `python -m workers.serve` (see deploy.yml).
      ports {
        container_port = 8080 # liveness shim (workers/serve.py)
      }

      dynamic "env" {
        for_each = local.backend_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.backend_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = false # CPU always allocated so the consume loop runs without requests
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      template[0].containers[0].command,
      template[0].containers[0].args,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_project_service.enabled,
    google_vpc_access_connector.connector,
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.secret_key,
    google_secret_manager_secret_iam_member.backend_secret_access,
  ]
}

# ── Web (Next.js) ────────────────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "web" {
  name                = "ledgercopilot-web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.run_web.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.web_max_instances
    }

    containers {
      image = var.bootstrap_image
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [
    google_project_service.enabled,
    google_vpc_access_connector.connector,
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.secret_key,
    google_secret_manager_secret_iam_member.backend_secret_access,
  ]
}

# ── Migration job — `alembic upgrade head` run by CI before traffic shifts ────
resource "google_cloud_run_v2_job" "migrate" {
  name                = "ledgercopilot-migrate"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.run_api.email
      max_retries     = 1

      vpc_access {
        connector = google_vpc_access_connector.connector.id
        egress    = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = var.bootstrap_image
        # command/args set by CI: `alembic upgrade head`.

        dynamic "env" {
          for_each = local.backend_secret_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      template[0].template[0].containers[0].command,
      template[0].template[0].containers[0].args,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_project_service.enabled,
    google_vpc_access_connector.connector,
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.secret_key,
    google_secret_manager_secret_iam_member.backend_secret_access,
  ]
}

# ── Public access: API and Web are browser-reachable; the worker is not ───────
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "web_public" {
  name     = google_cloud_run_v2_service.web.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
