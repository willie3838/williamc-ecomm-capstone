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
- `--output-dir PATH`: Directory where screenshots and reports will be saved (default: `reports/ui-audit`).
- `--visible`: Run Chrome with a visible window (requires active `$DISPLAY`). Default is modern headless Chrome.

## Audit Checks Performed:
1. **Initial Page Load**: Verifies page title, `#root` DOM mounting, CSS styles, and scans for 404 assets or uncaught console exceptions.
2. **Category Chip Filtering**: Clicks and asserts state toggles for "Laptops", "Tablets", "Headphones", "Smart Home", "TVs".
3. **Sample Comparison Cards**: Clicks popular comparison suggestion cards and observes smooth transition to loading state.
4. **Live Query Submission**: Enters complex queries into the search bar and triggers side-by-side spec comparison against live BigQuery & Gemini APIs.
5. **Comparison Matrix Inspection**: Verifies table rendering, attribute alignment, winner badge highlights, and product pricing cards.
6. **SKU Grounding Citations**: Verifies presence of clickable `[SKU: ...]` chips and checks link targets.
7. **Edge Cases**: Verifies single-item prompt feedback and out-of-catalog gracefully handled states.
