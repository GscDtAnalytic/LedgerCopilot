# Private networking so Cloud Run reaches Cloud SQL and Memorystore over private
# IP only — no database or cache is ever exposed to the public internet
#.

resource "google_compute_network" "vpc" {
  name                    = "ledgercopilot-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.enabled]
}

resource "google_compute_subnetwork" "main" {
  name          = "ledgercopilot-subnet"
  ip_cidr_range = "10.10.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# Serverless VPC Access connector — the bridge that lets Cloud Run send traffic
# into the VPC (to Cloud SQL private IP and Memorystore).
resource "google_vpc_access_connector" "connector" {
  name          = "lc-connector"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.8.0.0/28"
  min_instances = 2
  max_instances = 4
  depends_on    = [google_project_service.enabled]
}

# Private Service Access — reserved range + VPC peering used by Cloud SQL to get
# a private IP inside our network.
resource "google_compute_global_address" "private_service_range" {
  name          = "lc-private-service-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_range.name]
  depends_on              = [google_project_service.enabled]
}
