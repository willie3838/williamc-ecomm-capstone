---
name: selenium-ui-audit
description: Automated end-to-end Selenium testing and visual UX audit for the Best Buy catalog comparison web application. Runs headless Chrome locally on the Linux VM, interacting with elements, testing user flows, recording console errors, and capturing UI screenshots.
---

# Selenium UI/UX Audit Skill

This skill performs physical browser testing of the Best Buy Catalog Comparison application using Selenium and headless Google Chrome on Linux.

## Why This Skill Exists
- Bypasses Identity-Aware Proxy (IAP) barriers on Cloud Run by running the identical container bundle locally on `127.0.0.1:8080`.
- Connects directly to Google Cloud BigQuery and Vertex AI Gemini models using local developer credentials.
- Discovers frontend rendering bugs, console errors, 404 network assets, alignment problems, and user experience flaws automatically.

## Quick Start / Usage

To run a complete end-to-end audit:

```bash
uv run --with selenium python /usr/local/google/home/williamwlchan/.gemini/config/skills/selenium-ui-audit/scripts/run_audit.py
```

### Options:
- `--port PORT`: Specify local server port (default: auto-detects or uses `8080`).
- `--skip-server`: If your backend is already running on `--port`, skips starting a new server.
- `--output-dir PATH`: Directory where DOM telemetry (`audit_report.json`, `exploratory_dom_evidence.json`) and snapshots are saved (default: `reports/ui-audit`).
- `--visible`: Run Chrome with a visible window (requires active `$DISPLAY`). Default is modern headless Chrome.

## Division of Labor: Selenium (Code) vs. Argon (LLM Agent)

### 1. What Selenium (Python Code) Verifies Directly on the Live DOM Interface
- **DOM Mounting & Visibility**: Verifies `#root` mounting, `is_displayed()`, and non-zero bounding rects.
- **Layout Geometry & Console Health**: Checks horizontal viewport overflow (`scrollWidth <= clientWidth`), 404 assets, and uncaught JS console errors.
- **Interactive Flows & Latency**: Clicks category chips (`Laptops`, `Tablets`, `Headphones`, `Smart Home`, `TVs`), submits queries, verifies clickable `[SKU: ...]` citation links, and measures exact end-to-end latency (`ms`).
- **Live DOM State Extraction**: Exports the rendered DOM text (`product_card_titles`, `sku_citations`, `ai_comparison_summary`, and `body_excerpt`) directly to `stdout` and JSON (`reports/ui-audit/audit_report.json` and `reports/ui-audit/exploratory_dom_evidence.json`).

### 2. What the LLM Agent on the Harness (`argon`) Evaluates
Do **not** use Python regex/substring heuristics to grade semantic relevance or UX quality, and do **not** waste tokens reading PNG screenshots when the rendered DOM text is already extracted:
1. Run `exploratory_roamer.py` (optionally passing `--query "<custom adversarial or persona query>"` or `--scenarios-json <path>`):
   ```bash
   uv run --with selenium python skills/selenium-ui-audit/scripts/exploratory_roamer.py
   ```
2. Read the live DOM output from `stdout` or `reports/ui-audit/exploratory_dom_evidence.json`.
3. Evaluate whether the `product_card_titles`, `sku_citations`, and `ai_comparison_summary` semantically and accurately answer each user query (or gracefully decline out-of-catalog/adversarial requests), and write actionable UX/retrieval recommendations to `reports/ui-audit/exploratory_suggestions.md`.

