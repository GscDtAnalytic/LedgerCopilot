# Memorystore for Redis — backs the arq job queue and the API redis pool.
# Private (DIRECT_PEERING into the VPC); no AUTH needed inside the private network,
# but transit encryption is on.
resource "google_redis_instance" "cache" {
  name           = "ledgercopilot-redis"
  tier           = "BASIC"
  memory_size_gb = var.redis_memory_gb
  region         = var.region

  authorized_network      = google_compute_network.vpc.id
  connect_mode            = "DIRECT_PEERING"
  redis_version           = "REDIS_7_0"
  transit_encryption_mode = "DISABLED" # in-VPC only; arq/redis-py over the private peering

  depends_on = [google_project_service.enabled]
}

locals {
  redis_url = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
}
