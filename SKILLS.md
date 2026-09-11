# Operational Skills & Runbooks: Best Buy Catalog Comparison Agent

This document defines the standard operational procedures, CLI workflows, and automated recipes for developing, testing, deploying, and observing the **Best Buy Catalog Comparison Agent** on Google Cloud Platform (`fde-bestbuy-sandbox-dev-508321`).

---

## Table of Workflows

1. [Workflow 1: Buganizer & Taskflow Observability](#workflow-1-buganizer--taskflow-observability)
2. [Workflow 2: Test-Driven Development & Hillclimbing](#workflow-2-test-driven-development--hillclimbing)
3. [Workflow 3: Evaluation Flywheel & Benchmark Scoring](#workflow-3-evaluation-flywheel--benchmark-scoring)
4. [Workflow 4: Terraform Infrastructure Provisioning](#workflow-4-terraform-infrastructure-provisioning)
5. [Workflow 5: Cloud Build & Cloud Run Runtime Deployment](#workflow-5-cloud-build--cloud-run-runtime-deployment)
6. [Workflow 6: Capstone Rubric Self-Audit & Grading](#workflow-6-capstone-rubric-self-audit--grading)

---

## Workflow 1: Buganizer & Taskflow Observability

Maintains project issue tracking across Google Buganizer and Taskflow.

### Context Constants
- **Taskflow Workspace ID**: `6062895` ("Capstone")
- **Buganizer Component ID**: `2257265` (`Personal issues > williamwlchan`)
- **Active Iteration ID**: `6062377` (`Test (Current)`, Hotlist: `8948653`)

### Commands & Recipes
```bash
# 1. View all active tickets in the current sprint iteration
taskflow iterations view-items --iteration 6062377 --workspace 6062895

# 2. Create a new task ticket under the Capstone component
issues create \
  --title "[Ecomm]: <Title>" \
  --component 2257265 \
  --type BUG \
  --priority P2 \
  --severity S2 \
  --description "<Detailed requirements and acceptance criteria>"

# 3. Associate the created issue with the current iteration
taskflow iterations add-items \
  --iteration 6062377 \
  --workspace 6062895 \
  --issues <ISSUE_ID>

# 4. Update status when starting work
issues update status <ISSUE_ID> ASSIGNED
issues update assignees <ISSUE_ID> williamwlchan

# 5. Mark issue as resolved with verification evidence
issues update comments <ISSUE_ID> "Resolved in commit $(git rev-parse --short HEAD). Pytest unit tests (>=80% coverage) and evaluation benchmarks verified passing."
issues update status <ISSUE_ID> FIXED
```

---

## Workflow 2: Test-Driven Development & Hillclimbing

Autonomous outer-loop verification workflow. Ensures that every feature or bug fix is anchored by failing tests before implementation.

### Commands & Recipes
```bash
# 1. Activate virtual environment
cd /usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/backend
source .venv/bin/activate || python3 -m venv .venv && source .venv/bin/activate

# 2. Run Ruff linter and code formatter
ruff check . --fix
ruff format .

# 3. Run all unit tests with strict 80% coverage threshold
pytest --cov=src --cov-report=term-missing --cov-fail-under=80 tests/

# 4. Run tests with instant failure and verbose output
pytest -x -vv tests/

# 5. Run a specific test module or function
pytest tests/test_health.py -k "test_health_endpoint"
```

### Best Practices for Mocking BigQuery
When writing unit tests for `query_catalog`, do not make live network calls to BigQuery. Use `unittest.mock.MagicMock` to simulate the BigQuery client and row iterator:
```python
from unittest.mock import MagicMock, patch

@patch("google.cloud.bigquery.Client")
def test_query_catalog_mocked(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_row = {
        "sku": "6534606",
        "name": "MacBook Air 13.6\" Laptop - M3 chip",
        "brand": "Apple",
        "price": 1099.0,
        "specifications": {"ram_gb": 16, "storage_gb": 512}
    }
    mock_client.query.return_value.result.return_value = [mock_row]
    # Execute tool and assert
```

---

## Workflow 3: Evaluation Flywheel & Benchmark Scoring

Measures agent comparison accuracy, factual groundedness, and citation fidelity against the 80 benchmark product pairs.

### Commands & Recipes
```bash
# 1. Execute the full evaluation suite
cd /usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone
python3 -m evals.runner \
  --dataset evals/dataset/benchmark_queries.json \
  --output evals/reports/latest_eval_report.json \
  --judge-model gemini-1.5-flash

# 2. Evaluate specific product category only (e.g. Laptops)
python3 -m evals.runner \
  --dataset evals/dataset/benchmark_queries.json \
  --category Laptops

# 3. View summary metrics
python3 -m evals.analyze evals/reports/latest_eval_report.json
```

### Success Thresholds
- **Data Accuracy Score**: $\ge 0.98$ (Zero tolerance for fabricated specs).
- **Citation Faithfulness**: $\ge 0.95$ (All asserted specs must reference `[SKU: ...]`).
- **End-to-End P95 Latency**: $\le 3.0$ seconds.

---

## Workflow 4: Terraform Infrastructure Provisioning

Automates creation of BigQuery datasets, tables, IAM service accounts, and Cloud Run services in `fde-bestbuy-sandbox-dev-508321`.

### Commands & Recipes
```bash
# 1. Navigate to terraform directory
cd /usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/deployment/terraform

# 2. Initialize Terraform
terraform init

# 3. Format and validate configuration
terraform fmt -check
terraform validate

# 4. Generate speculative execution plan
terraform plan \
  -var="project_id=fde-bestbuy-sandbox-dev-508321" \
  -var="region=us-central1" \
  -out=tfplan

# 5. Apply infrastructure changes
terraform apply -auto-approve tfplan
```

---

## Workflow 5: Cloud Build & Cloud Run Runtime Deployment

Executes the production continuous delivery pipeline using Google Cloud Build.

### Commands & Recipes
```bash
# 1. Verify active GCP project configuration
gcloud config get-value project
# If not fde-bestbuy-sandbox-dev-508321:
gcloud config set project fde-bestbuy-sandbox-dev-508321

# 2. Submit build to Cloud Build
cd /usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone
gcloud builds submit \
  --config=deployment/cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_PROJECT_ID=fde-bestbuy-sandbox-dev-508321

# 3. Inspect Cloud Run service status
gcloud run services describe catalog-comparison-service \
  --region=us-central1 \
  --project=fde-bestbuy-sandbox-dev-508321

# 4. Test live service health endpoint
SERVICE_URL=$(gcloud run services describe catalog-comparison-service --region=us-central1 --format='value(status.url)')
curl -i "${SERVICE_URL}/health"
```

---

## Workflow 6: Capstone Rubric Self-Audit & Grading

Performs an automated or manual rubric compliance audit against the 31 core competencies defined in [RUBRIC.md](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/RUBRIC.md).

### Rubric Pillar Checklist
- [ ] **Pillar 1: Problem Definition & Scope** (Clear value prop, well-defined user personas, bounded catalog domain).
- [ ] **Pillar 2: System Architecture** (Cloud Run + BigQuery decoupled architecture, latency budget $\le 3.0$s, OTEL telemetry).
- [ ] **Pillar 3: Agentic Core** (Google ADK orchestration, anti-hallucination grounding prompt, parameterized BigQuery tool calling).
- [ ] **Pillar 4: GCP Production Engineering** (Terraform IaC, Cloud Build CI/CD, least-privilege service account, VPC-SC readiness).
- [ ] **Pillar 5: Quality, Evals & Delivery** (80-pair benchmark dataset, LLM-as-judge scoring, $\ge 80\%$ unit test coverage, Buganizer/Taskflow integration).
