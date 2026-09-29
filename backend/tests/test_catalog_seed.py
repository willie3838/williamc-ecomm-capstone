"""Unit tests verifying catalog seed integrity, schema conformity, and verified image URLs."""

import json
import re
from pathlib import Path


def test_catalog_seed_count_and_uniqueness():
    """Verify that catalog_seed.json has exactly 40 products with unique SKUs."""
    seed_file = Path(__file__).parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    assert seed_file.exists(), f"Seed catalog file not found at {seed_file}"

    with open(seed_file, encoding="utf-8") as f:
        products_data = json.load(f)

    assert len(products_data) == 40, f"Expected 40 products, got {len(products_data)}"

    skus = [p["sku"] for p in products_data]
    assert len(set(skus)) == 40, f"Expected 40 unique SKUs, got {len(set(skus))}"


def test_catalog_seed_schema_validation():
    """Verify that every product in catalog_seed.json validates cleanly against ProductRecord via BigQueryCatalogIngestor."""
    seed_file = Path(__file__).parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    from app.data.ingest import BigQueryCatalogIngestor

    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    records = ingestor.load_from_json(seed_file)
    assert len(records) == 40

    for record in records:
        assert record.sku
        assert record.price > 0
        assert record.rating is not None and 0.0 <= record.rating <= 5.0
        assert record.category in {"Laptops", "Tablets", "Headphones", "Smart Home", "TVs"}
        assert record.in_stock is True
        assert record.image_url.startswith(
            "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/"
        )


def test_catalog_seed_image_urls_match_verified_bestbuy_cdn():
    """Verify that all 40 products have valid Best Buy CDN image URLs starting with the pisces prefix."""
    seed_file = Path(__file__).parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    verified_file = Path(
        "/usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/.swarm/verified_image_urls.json"
    )

    with open(seed_file, encoding="utf-8") as f:
        products_data = json.load(f)

    cdn_pattern = re.compile(
        r"^https://pisces\.bbystatic\.com/image2/BestBuy_US/images/products/.+"
    )

    for p in products_data:
        image_url = p.get("image_url", "")
        assert image_url, f"SKU {p['sku']} has empty image_url"
        assert cdn_pattern.match(image_url), (
            f"SKU {p['sku']} image_url {image_url} does not match Best Buy CDN pattern"
        )

    if verified_file.exists():
        with open(verified_file, encoding="utf-8") as f:
            verified_urls = json.load(f)

        for p in products_data:
            sku = p["sku"]
            assert sku in verified_urls, f"SKU {sku} missing in verified_image_urls.json"
            assert p["image_url"] == verified_urls[sku], (
                f"SKU {sku} image_url {p['image_url']} does not match verified URL {verified_urls[sku]}"
            )


def test_frontend_backend_catalog_parity():
    """Verify that frontend catalogProducts.ts and backend catalog_seed.json have matching SKUs and image URLs."""
    seed_file = Path(__file__).parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    frontend_catalog = (
        Path(__file__).parent.parent.parent / "frontend" / "src" / "data" / "catalogProducts.ts"
    )

    assert seed_file.exists()
    assert frontend_catalog.exists()

    with open(seed_file, encoding="utf-8") as f:
        backend_products = json.load(f)

    backend_img_map = {p["sku"]: p["image_url"] for p in backend_products}

    frontend_content = frontend_catalog.read_text(encoding="utf-8")

    # Match sku and image_url blocks in typescript file
    ts_product_pattern = re.compile(
        r"sku:\s*['\"](?P<sku>\d+)['\"].*?image_url:\s*['\"](?P<img_url>https://[^'\"]+)['\"]",
        re.DOTALL,
    )

    matches = list(ts_product_pattern.finditer(frontend_content))
    assert len(matches) == 40, f"Expected 40 products parsed from frontend TS, found {len(matches)}"

    for m in matches:
        sku = m.group("sku")
        img_url = m.group("img_url")
        assert sku in backend_img_map, f"Frontend SKU {sku} not found in backend seed data"
        assert img_url == backend_img_map[sku], (
            f"Image mismatch for SKU {sku}: frontend={img_url} != backend={backend_img_map[sku]}"
        )
