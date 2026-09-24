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

### 3.5 Evaluation & Model Benchmark Cloud Run Jobs (`eval_job.tf`)
1. **Nightly Quality Evaluation Job**:
   - `google_cloud_run_v2_job.catalog_eval_job`: Executes the full 80-pair benchmark nightly at 02:00 UTC (`0 2 * * *`) via `google_cloud_scheduler_job.nightly_eval`.
2. **Weekly Foundation Model Benchmark Job**:
   - `google_cloud_run_v2_job.model_benchmark_job`: Executes the 4-candidate foundation model benchmark and per-stage ADK agent sweep (`python -m evals.benchmark_models --live`) weekly on Sunday at 03:00 UTC (`0 3 * * 0`) via `google_cloud_scheduler_job.weekly_model_benchmark`.

---

## 4. Cloud Build CI & Cloud Deploy CD Protocol (Rubric 6.1 Compliance)

The automated delivery pipeline cleanly decouples Continuous Integration (Cloud Build) from Continuous Delivery and Traffic Management (Cloud Deploy):

### 4.1 Cloud Build CI Pipeline (`cloudbuild.yaml`)
1. **Linter & Formatting Check**: Runs `ruff check backend/ evals/` and `ruff format --check backend/ evals/`.
2. **Unit Test Gate**: Runs `pytest --cov=src --cov-fail-under=80 tests/` inside containerized test harness.
3. **ADK Agent Conformance Gate**: Runs `evals/test_eval_adk.py` to assert ADK agent specs.
4. **Container Build**: Builds optimized container using Docker multi-stage build (`as builder` -> `as runner`).
5. **Artifact Push**: Pushes image tags `:${SHORT_SHA}` and `:latest` to Artifact Registry `us-central1-docker.pkg.dev/fde-bestbuy-sandbox-dev-508321/catalog-agent-repo/backend`.
6. **Release Registration**: Creates Google Cloud Deploy release targeting `catalog-service-pipeline`:
   `gcloud deploy releases create "rel-${SHORT_SHA}-..." --delivery-pipeline=catalog-service-pipeline ...`

### 4.2 Google Cloud Deploy CD Pipeline (`clouddeploy/`)
1. **Canary 0% Phase (`canary-0`)**: Cloud Deploy deploys the revision to Cloud Run with `automaticTrafficControl: true` and 0% public traffic under revision tag `candidate`.
2. **Automated Verification Probes**: Skaffold runs verify container (`curlimages/curl`) asserting `/health` (liveness HTTP 200), `/health/ready` (readiness HTTP 200), and `/openapi.json` (OpenAPI schema integrity).
3. **Automated Promotion (`stable-100`)**: Cloud Deploy Automation (`advanceRolloutRule`) shifts 100% of live traffic to the verified revision upon test success.
4. **Automated Rollback (`rollbackRule`)**: If verification fails, Cloud Deploy halts promotion and rolls back traffic immediately.

### 4.3 Ingress & IAM Authentication Protocol
- Under enterprise Domain-Restricted Sharing (DRS) Org Policies (`iam.allowedPolicyMemberDomains`), `allUsers` public access is restricted.
- Cloud Run service `catalog-comparison-service` requires `roles/run.invoker` for caller identities:
  - Runtime identity: `catalog-agent-sa@fde-bestbuy-sandbox-dev-508321.iam.gserviceaccount.com`
  - Compute runner: `499572810092-compute@developer.gserviceaccount.com`
  - Cloud Build pipeline: `499572810092@cloudbuild.gserviceaccount.com`
  - Administrator / UI tester: `admin@williamwlchan.altostrat.com`
- Verification probes (`deployment/clouddeploy/skaffold.yaml`) automatically acquire Google Compute Metadata OIDC Identity Tokens (`Metadata-Flavor: Google` with `audience=${TARGET_URL}`) to execute hermetic `/health` and `/health/ready` assertions.

---

## 5. Rollback Automation & Incident Recovery

1. **In-Flight Protection**:
   - Because candidate revisions are deployed with 0% public traffic, any test or probe failure terminates the rollout before user exposure. Production remains 100% intact on the previous stable revision.
2. **Automated CLI Rollback (`deployment/rollback.sh`)**:
   ```bash
   # Rollback via Cloud Deploy rollout rollback or direct Cloud Run traffic recovery
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

# Validate CI/CD Pipeline & Delivery Manifests Locally
python3 deployment/validate_pipeline.py

# Trigger CI/CD Pipeline via Google Cloud Build
gcloud builds submit \
  --config=deployment/cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_PROJECT_ID=fde-bestbuy-sandbox-dev-508321

# Manual Cloud Deploy Rollout Advance (if manual gate configured)
gcloud deploy rollouts advance <rollout-name> \
  --delivery-pipeline=catalog-service-pipeline \
  --region=us-central1

# Terraform Plan & Apply (Cloud Run lifecycle ignores dynamic traffic/image)
cd deployment/terraform
terraform init
terraform plan -var="project_id=fde-bestbuy-sandbox-dev-508321" -out=tfplan
terraform apply tfplan
```

---

## 7. Workload Identity Federation (WIF) for GitHub Actions CI/CD

To comply with Google Cloud Organization Policy constraints (`constraints/iam.managed.disableServiceAccountKeyCreation`), long-lived service account keys (`GCP_SA_KEY`) are prohibited.

Instead, GitHub Actions authenticates dynamically via **Workload Identity Federation (WIF)**:
- **Workload Identity Pool**: `github-actions-pool` (`projects/499572810092/locations/global/workloadIdentityPools/github-actions-pool`)
- **Pool Provider**: `github-provider` (OIDC issuer: `https://token.actions.githubusercontent.com`)
- **Attribute Restriction**: Restricted strictly to `attribute.repository == "willie3838/williamc-ecomm-capstone"`
- **Target Service Account**: `catalog-cicd-sa@fde-bestbuy-sandbox-dev-508321.iam.gserviceaccount.com` (granted `roles/iam.workloadIdentityUser`, `roles/iam.serviceAccountUser`, `roles/cloudbuild.builds.editor`, `roles/storage.admin`, and `roles/serviceusage.serviceUsageConsumer`)
- **Token Lifecycle**: GitHub dynamically mints a short-lived OIDC JWT per workflow step; Google STS exchanges it for a 1-hour short-lived OAuth2 access token with zero stored secrets.


