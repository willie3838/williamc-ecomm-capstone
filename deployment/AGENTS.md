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
├── cloudbuild.yaml            # Continuous Integration & Delivery pipeline
├── Dockerfile                 # Multi-stage production container for Cloud Run
└── terraform/
    ├── providers.tf           # Google Cloud provider configuration
    ├── variables.tf           # Input variables (project_id, region, etc.)
    ├── main.tf                # Core resources orchestration
    ├── bigquery.tf            # BigQuery catalog and telemetry tables
    ├── cloudrun.tf            # Cloud Run service definition
    ├── iam.tf                 # Least-privilege IAM bindings
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
3. **State Management**:
   - In production, Terraform state is stored in a GCS bucket (`gs://fde-bestbuy-sandbox-dev-508321-tfstate/`).

---

## 4. Cloud Build CI/CD Protocol

The automated pipeline defined in `cloudbuild.yaml` executes the following sequential steps:
1. **Linter Check**: Runs `ruff check .` and `ruff format --check .`.
2. **Unit Test Gate**: Runs `pytest --cov=src --cov-fail-under=80` inside the containerized test harness.
3. **Container Build**: Builds the optimized container using Docker multi-stage build.
4. **Artifact Push**: Pushes image to Artifact Registry `us-central1-docker.pkg.dev/fde-bestbuy-sandbox-dev-508321/catalog-agent-repo/backend:$COMMIT_SHA`.
5. **Cloud Run Release**: Deploys the revision to Cloud Run with zero downtime and traffic migration.

---

## 5. Standard Deployment Commands

```bash
# Verify GCP Project Context
gcloud config set project fde-bestbuy-sandbox-dev-508321

# Trigger Manual Cloud Build
gcloud builds submit \
  --config=deployment/cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_PROJECT_ID=fde-bestbuy-sandbox-dev-508321

# Terraform Plan & Apply
cd deployment/terraform
terraform init
terraform plan -var="project_id=fde-bestbuy-sandbox-dev-508321" -out=tfplan
terraform apply tfplan
```
