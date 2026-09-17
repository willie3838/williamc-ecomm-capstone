---
name: terraform-deploy
description: Plan, validate, and apply Terraform infrastructure for BigQuery, Cloud Run, and IAM in fde-bestbuy-sandbox-dev-508321.
---

# Terraform Deployment Skill

This skill governs provisioning and managing Google Cloud infrastructure for the **Best Buy Catalog Comparison Agent** using Terraform.

## Target Environment
- **Project ID**: `fde-bestbuy-sandbox-dev-508321`
- **Region**: `us-central1`
- **Terraform Directory**: `deployment/terraform`

---

## Operating Protocol

Execute the standard pipeline using the provided helper:
```bash
# Generate plan
bash skills/terraform-deploy/scripts/tf_run.sh plan

# Apply infrastructure changes
bash skills/terraform-deploy/scripts/tf_run.sh apply
```

Or execute manual commands:
```bash
cd deployment/terraform
terraform init
terraform fmt -check
terraform validate
terraform plan -var="project_id=fde-bestbuy-sandbox-dev-508321" -var="region=us-central1" -out=tfplan
terraform apply tfplan
```
