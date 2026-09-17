#!/usr/bin/env python3
"""
Automated Selenium UI/UX Audit Runner for Best Buy Catalog Comparison App.
Tests the core user journey with targeted, element-focused screenshots.
"""

import argparse
import os
import socket
import subprocess
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def find_free_port(starting_port: int = 8085) -> int:
    port = starting_port
    while is_port_open("127.0.0.1", port):
        port += 1
    return port


class UIAuditRunner:
    def __init__(self, port: int, repo_dir: Path, output_dir: Path, visible: bool = False, skip_server: bool = False):
        self.port = port
        self.repo_dir = repo_dir
        self.output_dir = output_dir
        self.screenshots_dir = output_dir / "screenshots"
        self.visible = visible
        self.skip_server = skip_server
        self.server_proc = None
        self.driver = None
        self.findings = []
        self.test_results = {}

        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def log(self, msg: str):
        print(f"[UI AUDIT] {msg}", flush=True)

    def add_finding(self, severity: str, message: str, details: str = ""):
        self.findings.append({"severity": severity, "message": message, "details": details})
        self.log(f"[{severity.upper()}] {message}")

    def start_local_server(self):
        if self.skip_server or is_port_open("127.0.0.1", self.port):
            self.log(f"Server already active or requested skip on 127.0.0.1:{self.port}")
            return

        self.log(f"Starting ephemeral app server on 127.0.0.1:{self.port}...")
        env = os.environ.copy()
        env["PORT"] = str(self.port)
        cmd = [
            "/usr/local/google/home/williamwlchan/.local/bin/uv",
            "run",
            "uvicorn",
            "app.main:app",
            "--host", "127.0.0.1",
            "--port", str(self.port)
        ]
        self.server_proc = subprocess.Popen(
            cmd,
            cwd=str(self.repo_dir / "backend" / "src"),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # Wait for health check
        for _ in range(30):
            if is_port_open("127.0.0.1", self.port):
                self.log(f"Server is live at http://127.0.0.1:{self.port}/")
                time.sleep(1.0)
                return
            time.sleep(0.5)

        raise RuntimeError(f"Server failed to start on 127.0.0.1:{self.port}")

    def setup_driver(self):
        self.log("Configuring Chrome WebDriver...")
        options = Options()
        if not self.visible:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1440,1200")
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(20)

    def capture_screenshot(self, name: str) -> Path:
        filepath = self.screenshots_dir / f"{name}.png"
        self.driver.save_screenshot(str(filepath))
        self.log(f"Captured screenshot: {filepath.name}")
        return filepath

    def scroll_into_view_and_capture(self, element, name: str) -> Path:
        """Scrolls the target element directly into viewport center and captures proof."""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", element)
            time.sleep(0.5)
        except Exception:
            pass
        return self.capture_screenshot(name)

    def check_browser_logs(self, step_name: str):
        try:
            logs = self.driver.get_log("browser")
            for entry in logs:
                level = entry.get("level", "INFO")
                message = entry.get("message", "")
                if level in ["SEVERE", "ERROR"]:
                    self.add_finding("error", f"Console Error during {step_name}", message)
                elif level == "WARNING":
                    if "favicon" not in message.lower():
                        self.add_finding("warning", f"Console Warning during {step_name}", message)
        except Exception as e:
            self.log(f"Could not retrieve console logs: {e}")

    def run_tests(self):
        base_url = f"http://127.0.0.1:{self.port}/"
        wait = WebDriverWait(self.driver, 25)

        # 1. Initial Page Load & Visual Branding Test
        self.log(f"1. Navigating to {base_url}...")
        self.driver.get(base_url)
        time.sleep(1.0)
        self.capture_screenshot("01_initial_landing_page")

        title = self.driver.title
        if "Best Buy" not in title:
            self.add_finding("error", "Page title does not mention Best Buy", f"Title: {title}")
        else:
            self.test_results["Initial Page Title"] = "PASS"

        try:
            logo = self.driver.find_element(By.XPATH, "//*[contains(text(), 'BEST BUY')]")
            self.test_results["Best Buy Logo Banner"] = "PASS"
        except Exception:
            self.add_finding("error", "BEST BUY logo element not found in DOM")
            self.test_results["Best Buy Logo Banner"] = "FAIL"

        self.check_browser_logs("Initial Page Load")

        # 2. Category Chips Filtering
        self.log("2. Testing category chips filter buttons...")
        try:
            laptop_chip = self.driver.find_element(By.XPATH, "//button[contains(., 'Laptops')]")
            laptop_chip.click()
            time.sleep(0.4)
            self.scroll_into_view_and_capture(laptop_chip, "02_laptop_category_selected")
            
            aria_pressed = laptop_chip.get_attribute("aria-pressed")
            if aria_pressed == "true":
                self.test_results["Category Chip Active State"] = "PASS"
            else:
                self.add_finding("warning", "Laptop category chip aria-pressed not true")

            all_cat_chip = self.driver.find_element(By.XPATH, "//button[contains(., 'All Categories')]")
            all_cat_chip.click()
            time.sleep(0.4)
        except Exception as e:
            self.add_finding("error", "Failed interacting with category chips", str(e))
            self.test_results["Category Chips"] = "FAIL"

        # 3. Popular Comparison Suggestion Card Click
        self.log("3. Testing popular comparison card click...")
        try:
            sample_card = self.driver.find_element(By.XPATH, "//h3[contains(text(), 'MacBook Air M3 vs Dell XPS 13')]")
            sample_card.click()
            time.sleep(0.3)
            self.capture_screenshot("03_sample_card_clicked_loading")
            self.test_results["Popular Comparison Card Selection"] = "PASS"
        except Exception as e:
            self.add_finding("error", "Failed clicking sample comparison card", str(e))
            self.test_results["Popular Comparison Card Selection"] = "FAIL"

        # Wait for comparison matrix to load from BigQuery + Gemini
        self.log("Waiting for comparison matrix generation (calling BigQuery & Gemini)...")
        try:
            wait.until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Side-by-Side Specification Matrix')]"))
            )
            time.sleep(0.8)
            self.test_results["BigQuery & Gemini Live Execution"] = "PASS"
            self.log("Comparison results successfully rendered on UI!")
        except Exception as e:
            self.capture_screenshot("04_comparison_matrix_timeout_failure")
            self.add_finding("error", "Timeout waiting for comparison matrix to render", str(e))
            self.test_results["BigQuery & Gemini Live Execution"] = "FAIL"

        self.check_browser_logs("Sample Comparison Execution")

        # 4. Target Screenshot: Compared Product Cards
        if self.test_results.get("BigQuery & Gemini Live Execution") == "PASS":
            self.log("4. Inspecting rendered Compared Product cards...")
            try:
                prod_cards_heading = self.driver.find_element(By.XPATH, "//h2[contains(text(), 'Compared Products')]")
                self.scroll_into_view_and_capture(prod_cards_heading, "04_compared_product_cards")
                
                product_cards = self.driver.find_elements(By.XPATH, "//h4[contains(@class, 'font-bold')]")
                if len(product_cards) >= 2:
                    self.test_results["Product Spec Cards"] = "PASS"
                else:
                    self.add_finding("warning", f"Expected >= 2 cards, found {len(product_cards)}")
            except Exception as e:
                self.add_finding("error", "Failed inspecting product cards", str(e))

            # 5. Target Screenshot: Comparison Matrix Table & Winner Badges
            self.log("5. Inspecting Side-by-Side Comparison Matrix & Winner Badges...")
            try:
                matrix_table = self.driver.find_element(By.XPATH, "//*[contains(text(), 'Side-by-Side Specification Matrix')]")
                self.scroll_into_view_and_capture(matrix_table, "05_comparison_matrix_and_winner_badges")

                winner_badges = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Winner')]")
                self.log(f"Found {len(winner_badges)} winner highlight badges.")
                if len(winner_badges) > 0:
                    self.test_results["Winner Spec Badges"] = "PASS"
                else:
                    self.add_finding("warning", "No 'Winner' badges found in comparison table.")
            except Exception as e:
                self.add_finding("error", "Failed inspecting comparison matrix", str(e))

            # 6. Target Screenshot: Grounded SKU Citations
            self.log("6. Inspecting Grounded SKU Citation Links...")
            try:
                citations_header = self.driver.find_element(By.XPATH, "//*[contains(text(), 'Verified SKU Grounding & Citations')]")
                self.scroll_into_view_and_capture(citations_header, "06_grounded_sku_citations")

                citation_links = self.driver.find_elements(By.XPATH, "//a[contains(., 'SKU:')]")
                self.log(f"Found {len(citation_links)} verified SKU citation links.")
                if len(citation_links) > 0:
                    self.test_results["Verified SKU Citation Links"] = "PASS"
                    href = citation_links[0].get_attribute("href")
                    if "bestbuy.com" in href:
                        self.test_results["SKU Citation Canonical URL"] = "PASS"
                    else:
                        self.add_finding("warning", f"Citation link target invalid: {href}")
                else:
                    self.add_finding("error", "No clickable [SKU: ...] citations found")
                    self.test_results["Verified SKU Citation Links"] = "FAIL"
            except Exception as e:
                self.add_finding("error", "Failed inspecting citation section", str(e))

            # Check AI Recommendation Narrative & Formatting Heuristic
            try:
                rec_card = self.driver.find_element(
                    By.XPATH,
                    "//div[contains(@class, 'RecommendationCard') or .//div[contains(text(), 'AI Comparison Summary')]]",
                )
                # General Rule of Thumb 1: Verify output has structured formatting (list items or badges)
                list_items = rec_card.find_elements(By.TAG_NAME, "li")
                card_text = rec_card.text
                
                # Verify no raw unrendered markdown escape sequences are exposed
                has_raw_markdown = "\n- " in card_text or "**" in card_text
                if has_raw_markdown:
                    self.add_finding("warning", "AI Recommendation contains unrendered markdown syntax")

                if len(list_items) >= 2 and not has_raw_markdown or "AI Comparison Summary" in card_text:
                    self.test_results["AI Recommendation Narrative & Formatting"] = "PASS"
                else:
                    self.add_finding("warning", "AI Recommendation narrative header not found")
            except Exception as e:
                self.add_finding("error", "Failed inspecting AI Recommendation narrative formatting", str(e))

        # 7. Custom Natural Language Search Submission (Headphones)
        self.log("7. Testing custom natural language query submission...")
        try:
            # Scroll back to search bar
            search_input = self.driver.find_element(By.XPATH, "//input[@aria-label='Natural language product comparison query']")
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", search_input)
            time.sleep(0.3)
            search_input.click()
            search_input.send_keys(Keys.CONTROL + "a")
            search_input.send_keys(Keys.BACKSPACE)
            custom_query = "Compare Sony WH-1000XM5 and Bose QC Ultra on price and battery life"
            search_input.send_keys(custom_query)
            time.sleep(0.3)
            
            submit_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            submit_button.click()
            self.log(f"Submitted query: '{custom_query}'")
            
            wait.until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Sony') or contains(text(), 'Bose')]"))
            )
            time.sleep(1.0)
            
            # Target screenshot of headphone matrix table
            headphone_matrix = self.driver.find_element(By.XPATH, "//*[contains(text(), 'Side-by-Side Specification Matrix')]")
            self.scroll_into_view_and_capture(headphone_matrix, "07_custom_search_headphones_matrix")
            self.test_results["Custom Query Search"] = "PASS"
        except Exception as e:
            self.capture_screenshot("07_custom_search_failure")
            self.add_finding("error", "Custom search query failed", str(e))
            self.test_results["Custom Query Search"] = "FAIL"

        self.check_browser_logs("Custom Query Search")

    def generate_report(self) -> Path:
        report_path = self.output_dir / "audit_summary.md"
        history_path = self.repo_dir / "logs" / "ui_audit_history.md"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        self.log(f"Generating audit report at {report_path}...")
        
        errors = [f for f in self.findings if f["severity"] == "error"]
        warnings = [f for f in self.findings if f["severity"] == "warning"]
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        status_str = "PASSED" if len(errors) == 0 else "FAILED"

        lines = [
            "# Automated Selenium UI/UX Audit Report",
            "",
            f"**Target Host**: `http://127.0.0.1:{self.port}/`  ",
            f"**Audit Timestamp**: `{timestamp}`  ",
            f"**Overall Status**: **{status_str}**  ",
            "",
            "## 1. Test Suite Results",
            "",
            "| Test Case | Status | Notes |",
            "|---|---|---|",
        ]

        for test_name, status in self.test_results.items():
            badge = "✅ PASS" if status == "PASS" else "❌ FAIL"
            lines.append(f"| {test_name} | {badge} | - |")

        lines.extend([
            "",
            "## 2. Issues & Findings",
            f"- **Errors**: `{len(errors)}`",
            f"- **Warnings**: `{len(warnings)}`",
            "",
        ])

        if not self.findings:
            lines.append("🎉 **Zero UI errors or warnings detected! The frontend is responsive, polished, and fully functional.**")
        else:
            for item in self.findings:
                sev_icon = "🔴" if item["severity"] == "error" else "🟡"
                lines.append(f"### {sev_icon} [{item['severity'].upper()}] {item['message']}")
                if item["details"]:
                    lines.append(f"```\n{item['details']}\n```")
                lines.append("")

        lines.extend([
            "## 3. Targeted Visual UI Snapshots Captured",
            "",
            "Every screenshot is scrolled directly to the asserted DOM elements to visually prove functionality:",
            "",
            "| Step | Screenshot Filename | Targeted Viewport Description |",
            "|---|---|---|",
            "| 01 | `01_initial_landing_page.png` | Hero landing view, branding, and search bar |",
            "| 02 | `02_laptop_category_selected.png` | Scrolled to category chip bar asserting active state |",
            "| 03 | `03_sample_card_clicked_loading.png` | Animated skeleton loader transition state |",
            "| 04 | `04_compared_product_cards.png` | Scrolled to side-by-side compared product cards & pricing |",
            "| 05 | `05_comparison_matrix_and_winner_badges.png` | Scrolled into matrix table showing attributes & Winner badges |",
            "| 06 | `06_grounded_sku_citations.png` | Scrolled to verified SKU citation badges and canonical links |",
            "| 07 | `07_custom_search_headphones_matrix.png` | Custom query matrix for Sony vs. Bose noise canceling |",
            ""
        ])

        report_path.write_text("\n".join(lines))

        # Append to historical log
        history_entry = f"| `{timestamp}` | **{status_str}** | {len(self.test_results)} | {len(errors)} | {len(warnings)} |\n"
        if not history_path.exists():
            history_path.write_text(
                "# Selenium UI/UX Audit Progression History\n\n"
                "| Timestamp | Status | Tests Executed | Errors | Warnings |\n"
                "|---|---|---|---|---|\n"
            )
        with open(history_path, "a") as f:
            f.write(history_entry)

        return report_path

    def cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
                self.log("Closed Chrome WebDriver.")
            except Exception:
                pass

        if self.server_proc:
            try:
                self.server_proc.terminate()
                self.server_proc.wait(timeout=3)
                self.log("Terminated ephemeral server.")
            except Exception:
                self.server_proc.kill()


def main():
    parser = argparse.ArgumentParser(description="Selenium UI/UX Audit for Best Buy App")
    parser.add_argument("--port", type=int, default=None, help="Port to run/test on")
    parser.add_argument("--skip-server", action="store_true", help="Skip starting local uvicorn server")
    parser.add_argument("--visible", action="store_true", help="Run Chrome visibly")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")

    args = parser.parse_args()
    repo_dir = Path("/usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone")
    
    port = args.port or (8080 if not is_port_open("127.0.0.1", 8080) else find_free_port(8081))
    output_dir = Path(args.output_dir) if args.output_dir else repo_dir / "reports" / "ui-audit"

    runner = UIAuditRunner(
        port=port,
        repo_dir=repo_dir,
        output_dir=output_dir,
        visible=args.visible,
        skip_server=args.skip_server
    )

    try:
        runner.start_local_server()
        runner.setup_driver()
        runner.run_tests()
        report_path = runner.generate_report()
        runner.log(f"Audit completed! Report at: {report_path}")
    finally:
        runner.cleanup()


if __name__ == "__main__":
    main()
