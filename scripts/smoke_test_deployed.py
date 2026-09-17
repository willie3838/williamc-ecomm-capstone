"""Smoke test verification for deployed Cloud Run service."""
import json
import google.auth
from google.auth.transport.requests import Request
import google.oauth2.id_token
import requests

url = "https://catalog-comparison-service-ocj5dik5ra-uc.a.run.app"
auth_req = Request()
target_audience = url
id_token = google.oauth2.id_token.fetch_id_token(auth_req, target_audience)

headers = {"Authorization": f"Bearer {id_token}"}

print("=== 1. Health Probe ===")
r = requests.get(f"{url}/health", headers=headers)
print(f"Status: {r.status_code}")
print(f"Body: {r.text}")

print("\n=== 2. Readiness Probe ===")
r = requests.get(f"{url}/health/ready", headers=headers)
print(f"Status: {r.status_code}")
print(f"Body: {r.text}")

print("\n=== 3. Compare API Live Query ===")
payload = {"query": "Compare MacBook Pro and Dell XPS 15", "max_results": 2}
r = requests.post(f"{url}/api/compare", json=payload, headers=headers)
print(f"Status: {r.status_code}")
try:
    data = r.json()
    print(json.dumps({
        "status": data.get("status"),
        "latency_ms": data.get("latency_ms"),
        "trace_id": data.get("trace_id"),
        "products_compared": [p.get("title") for p in data.get("comparison_matrix", {}).get("products", [])],
        "citations_count": len(data.get("citations", [])),
        "summary": data.get("summary")
    }, indent=2))
except Exception as e:
    print(r.text[:500])
