# Deployment & Infrastructure Agent Guide: GCP & Terraform

Welcome to the deployment and infrastructure directory of the **Best Buy Catalog Comparison Agent**. This module governs all Cloud Build CI/CD pipelines, Terraform Infrastructure as Code (IaC), container registries, and Google Cloud security posture.

---

## 1. Target GCP Environment

All infrastructure must strictly deploy into:
- **GCP Project ID**: `fde-bestbuy-sandbox-dev-508321`
- **Project Number**: `499572810092`
- **Primary Region**: `us-central1`
- **Artifact Registry**: `us-central1-docker.pkg.dev/fde-bestbuy-sandbox-dev-508321/catalog-agent-repo`
- **Cloud Run Service Name**: `catalog-comparison-service`
- **BigQuery Dataset**: `catalog`
- **Service Account**: `catalog-agent-sa@fde-bestbuy-sandbox-dev-508321.iam.gserviceaccount.com`

---

## 2. Directory Layout

```
deployment/
├── AGENTS.md                  # This file (DevOps & IaC guide)
├── cloudbuild.yaml            # Continuous Integration & Delivery pipeline (canary + promotion)
├── cloudbuild-rollback.yaml   # Automated Cloud Build emergency rollback pipeline
├── Dockerfile                 # Hardened multi-stage container (non-root appuser, healthcheck)
├── rollback.sh                # Instant traffic rollback CLI script
├── validate_pipeline.py       # Standalone pipeline and configuration validator
└── terraform/
    ├── providers.tf           # Google Cloud provider configuration
    ├── variables.tf           # Input variables (project_id, region, etc.)
    ├── main.tf                # Core resources orchestration
    ├── bigquery.tf            # BigQuery catalog and telemetry tables
    ├── cloudrun.tf            # Cloud Run service definition
    ├── iam.tf                 # Least-privilege IAM bindings
    ├── vpc_sc.tf              # VPC Service Controls perimeter (anti-exfiltration)
    └── outputs.tf             # Service URL and resource identifiers
```

---

## 3. Terraform Architecture & Best Practices

1. **Explicit Project ID Parameterization**:
   - Never hardcode project IDs in resource definitions; always reference `var.project_id`.
   - Default value is set to `fde-bestbuy-sandbox-dev-508321`.
2. **Least-Privilege IAM Bindings**:
   - The runtime service account `catalog-agent-sa` must only have:
     - `roles/bigquery.jobUser` on project level
     - `roles/bigquery.dataViewer` on dataset `catalog`
     - `roles/bigquery.dataEditor` on dataset `catalog_agent_telemetry`
     - `roles/cloudtrace.agent`
     - `roles/logging.logWriter`
3. **VPC Service Controls (VPC-SC Anti-Exfiltration)**:
   - Defined in `vpc_sc.tf`. Locks `bigquery.googleapis.com` and `storage.googleapis.com` inside a security perimeter to prevent unauthorized data exfiltration.
   - Public-facing Cloud Run (`run.googleapis.com`) and Vertex AI Gemini inference (`aiplatform.googleapis.com`) are intentionally excluded to ensure zero friction on user queries.
   - Configured with `spec` dry-run auditing (`vpc_sc_dry_run = true`) and hard enforcement status blocks.
   - Guarded by `enable_vpc_sc` toggle to permit clean local and sandbox testing.
4. **State Management**:
   - In production, Terraform state is stored in a GCS bucket (`gs://fde-bestbuy-sandbox-dev-508321-tfstate/`).

---

## 4. Cloud Build CI/CD Protocol (Rubric 6.1 Compliance)

The automated delivery pipeline defined in `cloudbuild.yaml` executes sequential quality gates and safe canary deployment:
1. **Linter & Formatting Check**: Runs `ruff check backend/` and `ruff format --check backend/`.
2. **Unit Test Gate**: Runs `pytest --cov=src --cov-fail-under=80 tests/` inside the containerized test harness.
3. **Container Build**: Builds optimized container using Docker multi-stage build (`as builder` -> `as runner`).
4. **Artifact Push**: Pushes image to Artifact Registry `us-central1-docker.pkg.dev/fde-bestbuy-sandbox-dev-508321/catalog-agent-repo/backend:$COMMIT_SHA` and `latest`.
5. **Canary Deployment**: Deploys revision to Cloud Run with `--no-traffic --tag candidate` to prevent premature traffic exposure.
6. **Smoke Test Health Probe**: Automated curl probes against candidate `${CANDIDATE_URL}/health` and `${CANDIDATE_URL}/health/ready` checking for HTTP 200 and `"status": "ok"`.
7. **Traffic Promotion**: Migrates 100% of live traffic to the verified revision via `gcloud run services update-traffic --to-latest`.
8. **Post-Promotion Verification**: Final liveness confirmation on the production service URL.

---

## 5. Rollback Automation & Incident Recovery

1. **In-Flight Protection**:
   - Because candidate revisions are deployed with `--no-traffic`, any test or probe failure terminates the build before live traffic routing. Production remains 100% intact on the previous stable revision.
2. **Automated CLI Rollback (`deployment/rollback.sh`)**:
   ```bash
   # Rollback to preceding stable revision automatically
   bash deployment/rollback.sh

   # Or rollback to a specific revision identifier
   bash deployment/rollback.sh catalog-comparison-service-00042-abc
   ```
3. **Cloud Build Rollback Pipeline (`deployment/cloudbuild-rollback.yaml`)**:
   ```bash
   gcloud builds submit \
     --config=deployment/cloudbuild-rollback.yaml \
     --substitutions=_REGION=us-central1,_PROJECT_ID=fde-bestbuy-sandbox-dev-508321
   ```

---

## 6. Standard Deployment & Validation Commands

```bash
# Verify GCP Project Context
gcloud config set project fde-bestbuy-sandbox-dev-508321

# Validate CI/CD Pipeline Configuration Locally
python3 deployment/validate_pipeline.py

# Trigger Full CI/CD Build via Google Cloud Build
gcloud builds submit \
  --config=deployment/cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_PROJECT_ID=fde-bestbuy-sandbox-dev-508321

# Terraform Plan & Apply
cd deployment/terraform
terraform init
terraform plan -var="project_id=fde-bestbuy-sandbox-dev-508321" -out=tfplan
terraform apply tfplan
```
