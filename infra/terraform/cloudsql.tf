# Cloud SQL for PostgreSQL 16 — private IP only, reached through the VPC connector.
resource "google_sql_database_instance" "main" {
  name             = "ledgercopilot-pg"
  database_version = "POSTGRES_16"
  region           = var.region

  # Guard against accidental `terraform destroy` of the production database.
  deletion_protection = true

  depends_on = [google_service_networking_connection.private_vpc]

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 10
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "06:00" # UTC — off-peak for São Paulo
    }

    ip_configuration {
      ipv4_enabled    = false # no public IP
      private_network = google_compute_network.vpc.id
    }

    database_flags {
      name  = "max_connections"
      value = "100"
    }
  }
}

resource "google_sql_database" "app" {
  name     = "ledgercopilot"
  instance = google_sql_database_instance.main.name
}

resource "random_password" "db" {
  length  = 32
  special = false # keep the URL clean (no percent-encoding needed)
}

resource "google_sql_user" "app" {
  name     = "ledger"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

locals {
  # SQLAlchemy async URL against the instance's private IP.
  database_url = "postgresql+asyncpg://${google_sql_user.app.name}:${random_password.db.result}@${google_sql_database_instance.main.private_ip_address}:5432/${google_sql_database.app.name}"
}
