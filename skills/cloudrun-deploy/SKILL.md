---
name: cloudrun-deploy
description: Build containers and deploy the comparison service to Google Cloud Run via Cloud Build in fde-bestbuy-sandbox-dev-508321.
---

# Cloud Run Deployment Skill

This skill governs the production continuous deployment pipeline using Google Cloud Build and Google Cloud Run.

## Target Parameters
- **Project ID**: `fde-bestbuy-sandbox-dev-508321`
- **Region**: `us-central1`
- **Service Name**: `catalog-comparison-service`
- **Artifact Registry**: `us-central1-docker.pkg.dev/fde-bestbuy-sandbox-dev-508321/catalog-agent-repo`

---

## Operating Protocol

Execute automated Cloud Build submission:
```bash
bash skills/cloudrun-deploy/scripts/deploy_service.sh
```

Verify live service health and response latency:
```bash
bash skills/cloudrun-deploy/resources/health_probe.sh
```

Or execute manual Cloud Build trigger:
```bash
gcloud builds submit \
  --config=deployment/cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_PROJECT_ID=fde-bestbuy-sandbox-dev-508321
```
