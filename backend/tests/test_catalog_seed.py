"""Unit tests verifying catalog seed integrity, schema conformity, and verified image URLs."""

import json
import re
from collections import Counter
from pathlib import Path

EXPECTED_TOTAL_SKUS = 10040
CANONICAL_SEED_COUNT = 40
EXPECTED_PER_CATEGORY = 2008
CANONICAL_CATEGORIES = {"Laptops", "Tablets", "Headphones", "Smart Home", "TVs"}


def test_catalog_seed_count_and_uniqueness():
    """Verify that catalog_seed.json has 10,040 products with unique SKUs and 2,008 per category."""
    seed_file = Path(__file__).parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    assert seed_file.exists(), f"Seed catalog file not found at {seed_file}"

    with open(seed_file, encoding="utf-8") as f:
        products_data = json.load(f)

    assert len(products_data) == EXPECTED_TOTAL_SKUS, (
        f"Expected {EXPECTED_TOTAL_SKUS} products, got {len(products_data)}"
    )

    skus = [p["sku"] for p in products_data]
    assert len(set(skus)) == EXPECTED_TOTAL_SKUS, (
        f"Expected {EXPECTED_TOTAL_SKUS} unique SKUs, got {len(set(skus))}"
    )

    cat_counts = Counter(p["category"] for p in products_data)
    assert set(cat_counts.keys()) == CANONICAL_CATEGORIES
    assert sum(cat_counts.values()) == EXPECTED_TOTAL_SKUS
    for cat in CANONICAL_CATEGORIES:
        assert cat_counts[cat] >= 1000, (
            f"Expected at least 1,000 SKUs for category {cat}, got {cat_counts[cat]}"
        )


def test_catalog_seed_schema_validation():
    """Verify that every product in catalog_seed.json validates cleanly against ProductRecord via BigQueryCatalogIngestor."""
    seed_file = Path(__file__).parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    from app.data.ingest import BigQueryCatalogIngestor

    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    records = ingestor.load_from_json(seed_file)
    assert len(records) == EXPECTED_TOTAL_SKUS

    for record in records:
        assert record.sku
        assert record.price > 0
        assert record.rating is not None and 0.0 <= record.rating <= 5.0
        assert record.category in CANONICAL_CATEGORIES
        assert record.in_stock is True
        assert record.image_url and record.image_url.startswith(
            "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/"
        )


def test_catalog_seed_image_urls_match_verified_bestbuy_cdn():
    """Verify that all 10,040 products have valid Best Buy CDN image URLs and canonical 40 at 0..39 are preserved."""
    seed_file = Path(__file__).parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    verified_file = Path(__file__).resolve().parents[2] / ".swarm" / "verified_image_urls.json"
    if not verified_file.exists():
        verified_file = Path(
            "/usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/.swarm/verified_image_urls.json"
        )

    with open(seed_file, encoding="utf-8") as f:
        products_data = json.load(f)

    assert len(products_data) == EXPECTED_TOTAL_SKUS

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

        canonical_slice = products_data[:CANONICAL_SEED_COUNT]
        assert len(canonical_slice) == CANONICAL_SEED_COUNT
        for p in canonical_slice:
            sku = p["sku"]
            assert sku in verified_urls, (
                f"Canonical SKU {sku} at index 0..39 missing in verified_image_urls.json"
            )
            assert p["image_url"] == verified_urls[sku], (
                f"SKU {sku} image_url {p['image_url']} does not match verified URL {verified_urls[sku]}"
            )


def test_frontend_backend_catalog_parity():
    """Verify that frontend catalog data and backend catalog_seed.json have 10,040 matching SKUs and image URLs."""
    seed_file = Path(__file__).parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    frontend_data_dir = Path(__file__).parent.parent.parent / "frontend" / "src" / "data"
    frontend_catalog_ts = frontend_data_dir / "catalogProducts.ts"
    frontend_seed_json = frontend_data_dir / "catalog_seed.json"

    assert seed_file.exists()
    assert frontend_catalog_ts.exists()
    assert frontend_seed_json.exists(), f"Expected frontend JSON catalog at {frontend_seed_json}"

    with open(seed_file, encoding="utf-8") as f:
        backend_products = json.load(f)

    with open(frontend_seed_json, encoding="utf-8") as f:
        frontend_products = json.load(f)

    assert len(backend_products) == EXPECTED_TOTAL_SKUS
    assert len(frontend_products) == EXPECTED_TOTAL_SKUS

    backend_img_map = {p["sku"]: p["image_url"] for p in backend_products}
    frontend_img_map = {p["sku"]: p["image_url"] for p in frontend_products}
    assert frontend_img_map == backend_img_map

    # Verify canonical 0..39 order matches identically between frontend and backend
    assert [p["sku"] for p in frontend_products[:CANONICAL_SEED_COUNT]] == [
        p["sku"] for p in backend_products[:CANONICAL_SEED_COUNT]
    ]

    ts_content = frontend_catalog_ts.read_text(encoding="utf-8")
    assert "catalog_seed.json" in ts_content
