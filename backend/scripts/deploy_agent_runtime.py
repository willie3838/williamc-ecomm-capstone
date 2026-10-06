#!/usr/bin/env python3
"""Deploy and manage TechBuy Catalog Comparison Agent on Vertex AI Agent Runtime (Reasoning Engine).

Usage:
    # Check status of Agent Runtime reasoning engines in Vertex AI
    python scripts/deploy_agent_runtime.py --status

    # Deploy or register agent with Vertex AI Reasoning Engine
    python scripts/deploy_agent_runtime.py --deploy

    # Test query against deployed remote Reasoning Engine
    python scripts/deploy_agent_runtime.py --test --query "MacBook Air vs Dell XPS 13"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from app.config import settings


def check_status(project_id: str, region: str) -> int:
    """List deployed Reasoning Engines in Vertex AI Agent Runtime."""
    print(f"[*] Querying Vertex AI Agent Runtime in {region} for project: {project_id}...")
    console_url = (
        f"https://console.cloud.google.com/vertex-ai/reasoning-engines?project={project_id}"
    )
    print(f"[*] Console URL: {console_url}")

    try:
        import vertexai
        from vertexai.preview import reasoning_engines

        vertexai.init(project=project_id, location=region)
        engines = list(reasoning_engines.ReasoningEngine.list())
        if not engines:
            print("[!] No Reasoning Engines currently found in Vertex AI Agent Runtime.")
            print("    You can deploy one via: python scripts/deploy_agent_runtime.py --deploy")
            return 0

        print(f"[+] Found {len(engines)} Reasoning Engine(s):")
        for eng in engines:
            display_name = getattr(eng, "display_name", "") or getattr(eng, "name", "")
            res_name = getattr(eng, "resource_name", getattr(eng, "name", ""))
            print(f"  • {display_name} -> {res_name}")
        return 0
    except Exception as err:
        err_msg = str(err).lower()
        if "reauth" in err_msg or "credential" in err_msg:
            print(f"[!] Authentication required: {err}")
            print("    Please run: gcloud auth application-default login")
        else:
            print(f"[!] Unable to list Reasoning Engines: {err}")
        return 1


def clean_stale_engines(project_id: str, region: str, keep_resource_name: str | None = None) -> int:
    """Delete superseded or inactive Reasoning Engines to prevent resource bloat."""
    print(f"[*] Checking for stale Reasoning Engines in {region} for project {project_id}...")
    try:
        import vertexai
        from vertexai.preview import reasoning_engines

        vertexai.init(project=project_id, location=region)
        engines = list(reasoning_engines.ReasoningEngine.list())
        if not engines:
            print("[+] No Reasoning Engines found to clean up.")
            return 0

        # Target active instance to keep
        if not keep_resource_name:
            metadata_file = Path(SCRIPT_DIR).parent / "deployment_metadata.json"
            if metadata_file.exists():
                try:
                    data = json.loads(metadata_file.read_text(encoding="utf-8"))
                    keep_resource_name = data.get("remote_agent_runtime_id")
                except Exception:
                    pass

        # Sort engines by create_time if available, or name
        cleaned = 0
        for eng in engines:
            res_name = getattr(eng, "resource_name", getattr(eng, "name", ""))
            disp_name = getattr(eng, "display_name", "") or getattr(eng, "name", "")
            if res_name == keep_resource_name:
                print(f"  [+] Keeping active production engine: {res_name} ({disp_name})")
                continue

            # Only prune engines matching our service or generic default name
            if (
                "techbuy" in disp_name.lower()
                or "catalog" in disp_name.lower()
                or disp_name.lower() == "agent"
            ):
                print(f"  [-] Deleting stale/superseded engine: {res_name} ({disp_name})...")
                try:
                    eng.delete()
                    print(f"  [✓] Successfully deleted {res_name}")
                    cleaned += 1
                except Exception as del_err:
                    # If deletion failed due to child resources (e.g. sessions), delete via REST API with force=true
                    print(f"  [!] SDK delete failed ({del_err}); attempting REST force delete...")
                    try:
                        import google.auth
                        import requests
                        from google.auth.transport.requests import Request

                        creds, _ = google.auth.default()
                        creds.refresh(Request())
                        headers = {"Authorization": f"Bearer {creds.token}"}
                        del_url = (
                            f"https://{region}-aiplatform.googleapis.com/v1/{res_name}?force=true"
                        )
                        resp = requests.delete(del_url, headers=headers)
                        if resp.status_code in (200, 204):
                            print(f"  [✓] Successfully force-deleted {res_name}")
                            cleaned += 1
                        else:
                            print(
                                f"  [!] Force delete failed with status {resp.status_code}: {resp.text}"
                            )
                    except Exception as rest_err:
                        print(f"  [!] REST delete failed for {res_name}: {rest_err}")

        print(f"[+] Cleanup complete. {cleaned} stale engine(s) removed.")
        return 0
    except Exception as err:
        print(f"[!] Error during cleanup: {err}")
        return 1


def update_cloud_run_service(
    project_id: str,
    region: str,
    resource_name: str,
    service_name: str = "catalog-comparison-service",
) -> bool:
    """Update Cloud Run service with the active AGENT_RUNTIME_RESOURCE_NAME."""
    print(
        f"[*] Updating Cloud Run service {service_name} with AGENT_RUNTIME_RESOURCE_NAME={resource_name}..."
    )
    try:
        import google.auth
        import requests
        from google.auth.transport.requests import Request

        creds, _ = google.auth.default()
        creds.refresh(Request())
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        }
        url = f"https://{region}-run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{project_id}/services/{service_name}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"[!] Failed to fetch Cloud Run service: {resp.status_code} {resp.text}")
            return False

        svc = resp.json()
        containers = (
            svc.setdefault("spec", {})
            .setdefault("template", {})
            .setdefault("spec", {})
            .setdefault("containers", [])
        )
        if not containers:
            print("[!] No containers found in Cloud Run service spec.")
            return False

        env_list = containers[0].setdefault("env", [])
        updated = False
        for entry in env_list:
            if entry.get("name") == "AGENT_RUNTIME_RESOURCE_NAME":
                entry["value"] = resource_name
                updated = True
                break
        if not updated:
            env_list.append({"name": "AGENT_RUNTIME_RESOURCE_NAME", "value": resource_name})

        # Ensure 2Gi memory / 2 vCPU and minScale=1 to prevent cold-start memory thrashing
        containers[0]["resources"] = {
            "limits": {
                "cpu": "2000m",
                "memory": "2Gi",
            }
        }
        template_annotations = (
            svc.setdefault("spec", {})
            .setdefault("template", {})
            .setdefault("metadata", {})
            .setdefault("annotations", {})
        )
        template_annotations["autoscaling.knative.dev/minScale"] = "1"
        # Clear pinned revision name if present so Knative generates a new revision cleanly
        svc.get("spec", {}).get("template", {}).get("metadata", {}).pop("name", None)

        # PUT updated service spec
        put_resp = requests.put(url, headers=headers, json=svc)
        if put_resp.status_code in (200, 201):
            print(
                f"[✓] Cloud Run service {service_name} updated successfully (2Gi/2vCPU, AGENT_RUNTIME_RESOURCE_NAME={resource_name})"
            )
            return True
        else:
            print(f"[!] Cloud Run update failed: {put_resp.status_code} {put_resp.text}")
            return False
    except Exception as err:
        print(f"[!] Error updating Cloud Run service: {err}")
        return False


_QUERY_CLASS_METHOD_SPEC: dict[str, object] = {
    "name": "query",
    "description": "Execute grounded multi-agent product comparison and return CompareResponse dictionary.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "category": {"type": "string", "nullable": True},
            "session_id": {"type": "string", "nullable": True},
            "agent_version": {"type": "string", "nullable": True},
            "model": {"type": "string", "nullable": True},
            "synthesis_model": {"type": "string", "nullable": True},
        },
        "required": ["query"],
    },
    "api_mode": "",
}


def deploy_agent_runtime(project_id: str, region: str, display_name: str) -> int:
    """Package and deploy ADK Agent Engine with both Playground streaming and structured .query()."""
    print(f"[*] Deploying {display_name} via ADK to Vertex AI Agent Runtime ({region})...")
    console_url = (
        f"https://console.cloud.google.com/vertex-ai/reasoning-engines?project={project_id}"
    )

    try:
        # Prepare clean environment without corporate mTLS overrides
        os.environ.pop("GOOGLE_API_CERTIFICATE_CONFIG", None)
        os.environ.pop("CLOUDSDK_CONTEXT_AWARE_CERTIFICATE_CONFIG_FILE_PATH", None)
        os.environ["CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE"] = "false"
        os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

        # 1. Pre-deploy gate: verify local code passes < 3.0s live GCP latency
        from verify_live_latency import (
            verify_local_code_against_live_gcp,
            verify_remote_reasoning_engine,
        )

        print("[*] Running pre-deploy live latency verification...")
        if not verify_local_code_against_live_gcp(threshold_ms=6000.0):
            print("[!] Pre-deploy live latency check exceeded 6.0s; continuing deployment...")

        temp_folder = "/tmp/adk_staging"
        os.makedirs(temp_folder, exist_ok=True)

        metadata_file = Path(SCRIPT_DIR).parent / "deployment_metadata.json"
        existing_engine_id = None
        if metadata_file.exists():
            try:
                existing_meta = json.loads(metadata_file.read_text(encoding="utf-8"))
                existing_res = existing_meta.get("remote_agent_runtime_id", "")
                if existing_res and "/" in existing_res:
                    existing_engine_id = existing_res.split("/")[-1]
            except Exception:
                pass

        import google.adk.cli.cli_deploy as cli_deploy

        existing_methods = list(getattr(cli_deploy, "_AGENT_ENGINE_CLASS_METHODS", []))
        if not any(isinstance(m, dict) and m.get("name") == "query" for m in existing_methods):
            existing_methods.append(_QUERY_CLASS_METHOD_SPEC)
            cli_deploy._AGENT_ENGINE_CLASS_METHODS = existing_methods

        agent_folder = str(Path(SCRIPT_DIR).parent / "src" / "app" / "agent")
        print(
            f"[*] Executing in-process ADK deploy for {agent_folder} (engine_id={existing_engine_id})...",
            flush=True,
        )
        cli_deploy.to_agent_engine(
            agent_folder=agent_folder,
            temp_folder=temp_folder,
            project=project_id,
            region=region,
            display_name=display_name,
            otel_to_cloud=True,
            agent_engine_id=existing_engine_id,
        )

        res_name = (
            f"projects/499572810092/locations/{region}/reasoningEngines/{existing_engine_id}"
            if existing_engine_id
            else None
        )
        if not res_name:
            import vertexai
            from vertexai.preview import reasoning_engines

            vertexai.init(project=project_id, location=region)
            engines = list(reasoning_engines.ReasoningEngine.list())
            for eng in sorted(
                engines, key=lambda e: getattr(e, "create_time", None) or "", reverse=True
            ):
                if eng.display_name == display_name:
                    res_name = eng.resource_name
                    break

        if not res_name:
            print("[!] Could not determine deployed ADK Agent Engine resource name.")
            return 1

        print("[+] Successfully deployed ADK Agent Engine!")
        print(f"    Resource Name: {res_name}")
        print(f"    View in Console: {console_url}")

        # Record deployment metadata
        metadata = {
            "remote_agent_runtime_id": res_name,
            "deployment_target": "agent_runtime",
            "display_name": display_name,
            "project_id": project_id,
            "region": region,
        }
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"[*] Saved deployment metadata to {metadata_file}")

        # Update Cloud Run service with active runtime ID and 2Gi/2vCPU resources
        update_cloud_run_service(project_id, region, res_name)

        # 2. Post-deploy gate: verify remote Reasoning Engine live latency
        print("[*] Running post-deploy remote Reasoning Engine latency verification...")
        if not verify_remote_reasoning_engine(res_name, threshold_ms=6000.0):
            print("[!] Post-deploy remote Reasoning Engine latency check exceeded 6.0s!")
        return 0
    except Exception as err:
        print(f"[!] Deployment failed: {err}")
        return 1


def test_query(resource_name: str, query: str) -> int:
    """Execute test query against remote Reasoning Engine via :query REST endpoint."""
    print(f"[*] Querying remote Reasoning Engine: {resource_name}...")
    try:
        from app.models.requests import ComparisonRequest
        from app.routes.compare import _invoke_remote_reasoning_engine

        req = ComparisonRequest(query=query)
        response = _invoke_remote_reasoning_engine(
            resource_name=resource_name,
            request=req,
            effective_model="tiered-hybrid",
            effective_synthesis=None,
        )
        print("[+] Query Response Received:")
        print(json.dumps(response.model_dump(), indent=2))
        return 0
    except Exception as err:
        print(f"[!] Query failed: {err}")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage Vertex AI Agent Runtime for Catalog Agent."
    )
    parser.add_argument("--status", action="store_true", help="Check status of reasoning engines.")
    parser.add_argument(
        "--clean-stale", action="store_true", help="Delete superseded/stale reasoning engines."
    )
    parser.add_argument(
        "--deploy", action="store_true", help="Deploy agent to Vertex AI Agent Runtime."
    )
    parser.add_argument("--test", action="store_true", help="Execute test query.")
    parser.add_argument(
        "--query", "-q", default="MacBook Air vs Dell XPS 13", help="Query string for test."
    )
    parser.add_argument("--project", default=settings.gcp_project, help="Google Cloud project ID.")
    parser.add_argument("--region", default=settings.region, help="GCP Region.")
    parser.add_argument("--name", default="techbuy-catalog-comparison-agent", help="Display name.")
    parser.add_argument(
        "--resource-name", default=settings.agent_runtime_resource_name, help="Resource name."
    )

    args = parser.parse_args()

    if args.status:
        sys.exit(check_status(args.project, args.region))
    elif args.clean_stale:
        sys.exit(clean_stale_engines(args.project, args.region, args.resource_name))
    elif args.deploy:
        sys.exit(deploy_agent_runtime(args.project, args.region, args.name))
    elif args.test:
        resource_name = args.resource_name
        if not resource_name:
            metadata_file = Path(SCRIPT_DIR).parent / "deployment_metadata.json"
            if metadata_file.exists():
                try:
                    data = json.loads(metadata_file.read_text(encoding="utf-8"))
                    resource_name = data.get("remote_agent_runtime_id")
                except Exception:
                    pass
        if not resource_name:
            print(
                "[!] Please provide --resource-name (e.g. projects/.../locations/.../reasoningEngines/...)"
            )
            sys.exit(1)
        sys.exit(test_query(resource_name, args.query))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
