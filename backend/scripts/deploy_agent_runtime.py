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
import subprocess
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

        # PUT updated service spec
        put_resp = requests.put(url, headers=headers, json=svc)
        if put_resp.status_code in (200, 201):
            print(
                f"[✓] Cloud Run service {service_name} updated successfully with AGENT_RUNTIME_RESOURCE_NAME={resource_name}"
            )
            return True
        else:
            print(f"[!] Cloud Run update failed: {put_resp.status_code} {put_resp.text}")
            return False
    except Exception as err:
        print(f"[!] Error updating Cloud Run service: {err}")
        return False


def deploy_agent_runtime(project_id: str, region: str, display_name: str) -> int:
    """Package and deploy ADK Agent Engine to Vertex AI Agent Runtime."""
    print(f"[*] Deploying {display_name} via ADK to Vertex AI Agent Runtime ({region})...")
    console_url = (
        f"https://console.cloud.google.com/vertex-ai/reasoning-engines?project={project_id}"
    )

    try:
        # Prepare clean environment without corporate mTLS overrides
        env = os.environ.copy()
        env.pop("GOOGLE_API_CERTIFICATE_CONFIG", None)
        env.pop("CLOUDSDK_CONTEXT_AWARE_CERTIFICATE_CONFIG_FILE_PATH", None)
        env["CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE"] = "false"
        env["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

        temp_folder = "/tmp/adk_staging"
        os.makedirs(temp_folder, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "google.adk.cli",
            "deploy",
            "agent_engine",
            "src/app/agent",
            f"--project={project_id}",
            f"--region={region}",
            f"--display_name={display_name}",
            "--otel_to_cloud",
            f"--temp_folder={temp_folder}",
        ]

        print(f"[*] Executing ADK deploy: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, cwd=str(Path(SCRIPT_DIR).parent), env=env, capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"[!] ADK deploy failed with code {result.returncode}: {result.stderr}")
            return result.returncode

        # Locate newest reasoning engine created with this display name
        import vertexai
        from vertexai.preview import reasoning_engines

        vertexai.init(project=project_id, location=region)
        engines = list(reasoning_engines.ReasoningEngine.list())
        target_engine = None
        for eng in sorted(
            engines, key=lambda e: getattr(e, "create_time", None) or "", reverse=True
        ):
            if eng.display_name == display_name:
                target_engine = eng
                break

        res_name = target_engine.resource_name if target_engine else None
        if not res_name:
            print("[!] Could not determine deployed ADK Agent Engine resource name.")
            return 1

        print("[+] Successfully deployed ADK Agent Engine!")
        print(f"    Resource Name: {res_name}")
        print(f"    View in Console: {console_url}")

        # Record deployment metadata
        metadata_file = Path(SCRIPT_DIR).parent / "deployment_metadata.json"
        metadata = {
            "remote_agent_runtime_id": res_name,
            "deployment_target": "agent_runtime",
            "display_name": display_name,
            "project_id": project_id,
            "region": region,
        }
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"[*] Saved deployment metadata to {metadata_file}")

        # Update Cloud Run service with active runtime ID
        update_cloud_run_service(project_id, region, res_name)
        return 0
    except Exception as err:
        print(f"[!] Deployment failed: {err}")
        return 1


def test_query(resource_name: str, query: str) -> int:
    """Execute test query against remote Reasoning Engine."""
    print(f"[*] Querying remote Reasoning Engine: {resource_name}...")
    try:
        from vertexai.preview import reasoning_engines

        remote_agent = reasoning_engines.ReasoningEngine(resource_name)
        response = remote_agent.query(query=query)
        print("[+] Query Response Received:")
        print(json.dumps(response, indent=2))
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
