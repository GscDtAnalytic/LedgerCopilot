# LedgerCopilot — Production Infrastructure (GCP)

Terraform for the production environment on Google Cloud. One GCP project, region
`southamerica-east1` (São Paulo — keeps financial-document data in Brazil).

## Architecture

```
                         Internet
                            │
        ┌───────────────────┴───────────────────┐
        ▼                                        ▼
  Cloud Run: web (Next.js)              Cloud Run: api (FastAPI)  ──► Secret Manager
        │  NEXT_PUBLIC_API_URL                    │                    (db-url, jwt, anthropic key)
        └──────── browser fetch ──────────────────┤
                                                  │  VPC connector (PRIVATE_RANGES_ONLY)
   Cloud Run: worker (arq, min=1, ┐               │
   CPU always on, internal only)  ├──────────────►│──► Cloud SQL Postgres 16 (private IP)
                                  ┘               ├──► Memorystore Redis (private)
                                                  └──► GCS bucket (documents / bronze)

  Artifact Registry ◄── images ── GitHub Actions ──(WIF, keyless)── deploy
```

- **api / web / worker** — Cloud Run services. Terraform owns their shape; CI owns
  the image (`ignore_changes`).
- **worker** — arq queue consumer; `min-instances=1` + CPU-always-on, internal
  ingress only, liveness via `workers/serve.py`.
- **Cloud SQL / Memorystore** — private IP only, reachable through the VPC connector.
- **GCS** — bronze document storage (`packages/storage/gcs.py`), versioned + private.
- **Secret Manager** — JWT key + DB URL (Terraform-managed) and the Anthropic key
  (added out of band).
- **WIF** — GitHub Actions authenticate keylessly; no JSON SA key exists.

## One-time bootstrap

Run by a human with `Owner` (or equivalent) on the project. CI never bootstraps.

```bash
# 0. Pick names
export PROJECT_ID=your-gcp-project-id
export REGION=southamerica-east1
export TF_STATE_BUCKET=${PROJECT_ID}-tf-state

# 1. Remote state bucket (versioned)
gcloud storage buckets create gs://${TF_STATE_BUCKET} \
  --project=${PROJECT_ID} --location=${REGION} --uniform-bucket-level-access
gcloud storage buckets update gs://${TF_STATE_BUCKET} --versioning

# 2. Configure + apply (creates APIs, network, DB, Redis, bucket, Cloud Run, WIF…)
cp terraform.tfvars.example terraform.tfvars   # edit project_id
terraform init -backend-config="bucket=${TF_STATE_BUCKET}"
terraform apply

# 3. Provide the real Anthropic key (Cloud Run won't start without a version)
printf '%s' "sk-ant-..." | gcloud secrets versions add anthropic-api-key --data-file=-
```

> First `apply` creates the Cloud Run services with a placeholder image
> (`var.bootstrap_image`). The real images arrive on the first `deploy` run.

## Wire up CI/CD (GitHub → repo → Settings → Variables)

`terraform output` prints the values. Set these **repository variables**:

| Variable             | Source (`terraform output`)     |
| -------------------- | ------------------------------- |
| `GCP_PROJECT_ID`     | your project id                 |
| `GCP_REGION`         | `southamerica-east1`            |
| `GCP_WIF_PROVIDER`   | `workload_identity_provider`    |
| `GCP_DEPLOYER_SA`    | `deployer_service_account`      |
| `TF_STATE_BUCKET`    | the bucket from step 1          |
| `GCP_TF_SA`          | a Terraform-admin SA (see below)|

Create a `production` **environment** (Settings → Environments) and add required
reviewers — this gates `terraform apply` and the `deploy` job.

### Terraform-admin SA (for the optional `terraform.yml apply`)

`deployer_service_account` is intentionally narrow (deploy + push images only). To
run `terraform apply` from CI you need a broader admin SA and must let the repo
impersonate it:

```bash
gcloud iam service-accounts create lc-tf-admin --project=$PROJECT_ID
# Grant the roles your infra needs (editor + project IAM admin is the simplest
# starting point; tighten later). Then bind WIF impersonation:
gcloud iam service-accounts add-iam-policy-binding \
  lc-tf-admin@${PROJECT_ID}.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/$(terraform output -raw workload_identity_provider | sed 's#/providers/.*##')/attribute.repository/GscDtAnalytic/LedgerCopilot"
```

Most teams keep `apply` manual/local at first and only use CI for `plan`.

## Day-2

- **Deploy** — merge to the default branch → `deploy.yml` builds images, runs
  migrations (`alembic upgrade head` as a Cloud Run Job), and rolls out api → worker → web.
- **Rotate the JWT key** — `terraform taint random_password.jwt_secret && terraform apply`.
- **Rotate the Anthropic key** — add a new secret version; services pick up `latest`
  on next revision.
- **Scale** — tune `db_tier`, `redis_memory_gb`, `api_max_instances` in `terraform.tfvars`.
- **Destroy** — `deletion_protection = true` on Cloud SQL guards the DB; remove it
  before `terraform destroy`.
