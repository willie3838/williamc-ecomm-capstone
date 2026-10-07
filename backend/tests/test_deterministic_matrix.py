"""Comprehensive unit tests for the deterministic greater-set matrix evaluator and hybrid router.

Covers:
1. Matrix generation across 2 to 5 products with greater-set union of non-warehouse specs.
2. Missing specs automatically lose to products with valid spec values.
3. Strict tie resolution: subset ties populate winner_skus, all-way ties leave winner_sku=None and winner_skus=[].
4. Polarity evaluation across all 5 categories (Laptops, Tablets, Headphones, Smart Home, TVs).
5. Synonymous key normalization (e.g. panel_type vs display_technology, screen_size_in vs display_size_in).
6. Hybrid routing in synthesize_comparison_with_llm (clean query 0ms deterministic vs contextual preference call).
"""

from unittest.mock import MagicMock

import pytest

from app.agent.matrix_evaluator import (
    MatrixEvaluator,
    extract_numeric,
    format_spec_label,
    format_spec_value,
    normalize_spec_key,
    parse_boolean,
    parse_resolution_pixels,
    score_panel_tier,
    score_processor_tier,
)
from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import ProductSpec


# Fixtures for 5 products across various categories
@pytest.fixture
def sample_laptop_1() -> ProductSpec:
    return ProductSpec(
        sku="LAP-1",
        name="UltraBook Pro 14",
        brand="BrandX",
        category="Laptops",
        price=1299.99,
        rating=4.7,
        specifications={
            "ram_gb": 32,
            "storage_gb": 1000,
            "battery_life_hours": 18.0,
            "weight_lbs": 2.8,
            "display_size_in": 14.2,
            "display_resolution": "2880 x 1800 OLED",
            "processor": "Apple M3 Pro",
            "panel_type": "OLED",
            "refresh_rate_hz": 120,
            "gpu": "14-core GPU",
        },
    )


@pytest.fixture
def sample_laptop_2() -> ProductSpec:
    return ProductSpec(
        sku="LAP-2",
        name="SlimBook 13",
        brand="BrandY",
        category="Laptops",
        price=999.99,
        rating=4.5,
        specifications={
            "ram_gb": 16,
            "storage_gb": 512,
            "battery_life_hours": 12.0,
            "weight_lbs": 2.5,
            "display_size_in": 13.3,
            "display_resolution": "1920 x 1080 FHD",
            "processor": "Intel Core i5",
            "panel_type": "IPS",
            "refresh_rate_hz": 60,
        },
    )


@pytest.fixture
def sample_tablet() -> ProductSpec:
    return ProductSpec(
        sku="TAB-1",
        name="Creator Tab 11",
        brand="BrandZ",
        category="Tablets",
        price=799.99,
        rating=4.6,
        specifications={
            "ram_gb": 8,
            "storage_gb": 256,
            "battery_life_hours": 10.0,
            "weight_lbs": 1.1,
            "display_size_in": 11.0,
            "stylus_included": True,
            "display_resolution": "2388 x 1668 Liquid Retina",
            "panel_type": "Liquid Retina",
        },
    )


@pytest.fixture
def sample_headphones_1() -> ProductSpec:
    return ProductSpec(
        sku="HP-1",
        name="QuietSound 900",
        brand="AudioMaster",
        category="Headphones",
        price=349.99,
        rating=4.8,
        specifications={
            "driver_size_mm": 40,
            "battery_life_hours": 30.0,
            "noise_canceling": True,
            "weight_oz": 8.5,
            "bluetooth_version": "5.3",
        },
    )


@pytest.fixture
def sample_headphones_2() -> ProductSpec:
    return ProductSpec(
        sku="HP-2",
        name="BassBeat 500",
        brand="AudioBeat",
        category="Headphones",
        price=199.99,
        rating=4.3,
        specifications={
            "driver_size_mm": 30,
            "battery_life_hours": 20.0,
            "noise_canceling": False,
            "weight_oz": 10.2,
            "bluetooth_version": "5.0",
        },
    )


@pytest.fixture
def sample_smarthome_1() -> ProductSpec:
    return ProductSpec(
        sku="SH-1",
        name="Guardian Cam Pro",
        brand="HomeSecure",
        category="Smart Home",
        price=149.99,
        rating=4.6,
        specifications={
            "sensor_range_ft": 50,
            "sensor_included": True,
            "battery_life_months": 6,
        },
    )


@pytest.fixture
def sample_smarthome_2() -> ProductSpec:
    return ProductSpec(
        sku="SH-2",
        name="Basic Cam",
        brand="HomeSecure",
        category="Smart Home",
        price=89.99,
        rating=4.2,
        specifications={
            "sensor_range_ft": 25,
            "sensor_included": False,
            "battery_life_months": 3,
        },
    )


@pytest.fixture
def sample_tv_1() -> ProductSpec:
    return ProductSpec(
        sku="TV-1",
        name="VisionMaster OLED 65",
        brand="ScreenKing",
        category="TVs",
        price=1899.99,
        rating=4.9,
        specifications={
            "screen_size_in": 65.0,
            "hdmi_ports": 4,
            "response_time_ms": 0.1,
            "resolution": "4K (3840 x 2160)",
            "display_technology": "OLED evo",
            "refresh_rate_hz": 120,
        },
    )


@pytest.fixture
def sample_tv_2() -> ProductSpec:
    return ProductSpec(
        sku="TV-2",
        name="ClearView QLED 55",
        brand="ScreenKing",
        category="TVs",
        price=899.99,
        rating=4.4,
        specifications={
            "display_size_in": 55.0,
            "hdmi_ports": 3,
            "response_time_ms": 4.0,
            "display_resolution": "1920 x 1080",
            "panel_type": "QLED",
            "refresh_rate_hz": 60,
        },
    )


# -------------------------------------------------------------------------
# 1. Greater-Set Union across 2 to 5 Products
# -------------------------------------------------------------------------
def test_greater_set_union_up_to_5_products(
    sample_laptop_1: ProductSpec,
    sample_laptop_2: ProductSpec,
    sample_tablet: ProductSpec,
    sample_headphones_1: ProductSpec,
    sample_smarthome_1: ProductSpec,
) -> None:
    """Verify matrix evaluator builds comparative rows for the union of all non-warehouse specs for 2 to 5 products."""
    evaluator = MatrixEvaluator()

    # 2 Products
    matrix_2 = evaluator.evaluate_matrix([sample_laptop_1, sample_laptop_2])
    features_2 = {r.feature for r in matrix_2}
    assert "Price" in features_2
    assert "Customer Rating" in features_2
    assert "Memory (RAM)" in features_2
    assert "Storage (SSD)" in features_2
    assert "Gpu" in features_2  # Laptop 1 has GPU, Laptop 2 lacks GPU -> included in greater set!

    # 5 Products
    products_5 = [
        sample_laptop_1,
        sample_laptop_2,
        sample_tablet,
        sample_headphones_1,
        sample_smarthome_1,
    ]
    matrix_5 = evaluator.evaluate_matrix(products_5)
    features_5 = {r.feature for r in matrix_5}

    # All unique non-warehouse specs across all 5 products must appear
    assert "Stylus Included" in features_5  # From tablet
    assert "Active Noise Canceling" in features_5  # From headphones
    assert "Sensor Detection Range" in features_5  # From smarthome
    assert "Gpu" in features_5  # From laptop 1

    # Warehouse metadata must be excluded
    for r in matrix_5:
        f_low = r.feature.lower()
        assert "upc" not in f_low
        assert "model_number" not in f_low
        assert "shipping_tier" not in f_low
        assert "taxonomy" not in f_low


# -------------------------------------------------------------------------
# 2. Missing Specs Automatically Lose
# -------------------------------------------------------------------------
def test_missing_spec_automatically_loses(
    sample_laptop_1: ProductSpec,
    sample_laptop_2: ProductSpec,
    sample_tablet: ProductSpec,
) -> None:
    """Verify that products missing a specification automatically lose to products with valid values."""
    evaluator = MatrixEvaluator()

    # Laptop 1 has 'gpu' (14-core GPU), Laptop 2 has no 'gpu'
    matrix_laptops = evaluator.evaluate_matrix([sample_laptop_1, sample_laptop_2])
    rows = {r.feature: r for r in matrix_laptops}
    assert "Gpu" in rows
    assert rows["Gpu"].winner_sku == "LAP-1"
    assert rows["Gpu"].winner_skus == ["LAP-1"]

    # Tablet has 'stylus_included: True', Laptops have no stylus_included
    matrix_all = evaluator.evaluate_matrix([sample_laptop_1, sample_tablet])
    rows_all = {r.feature: r for r in matrix_all}
    assert "Stylus Included" in rows_all
    assert rows_all["Stylus Included"].winner_sku == "TAB-1"
    assert rows_all["Stylus Included"].winner_skus == ["TAB-1"]


def test_missing_spec_loses_among_3_products(
    sample_laptop_1: ProductSpec,
    sample_laptop_2: ProductSpec,
    sample_tablet: ProductSpec,
) -> None:
    """Verify that when 1 product misses a spec and the other 2 have it, the missing product loses."""
    evaluator = MatrixEvaluator()
    # Refresh rate: Laptop 1 (120 Hz), Laptop 2 (60 Hz), Tablet (None)
    matrix = evaluator.evaluate_matrix([sample_laptop_1, sample_laptop_2, sample_tablet])
    rows = {r.feature: r for r in matrix}
    assert "Refresh Rate" in rows
    assert rows["Refresh Rate"].winner_sku == "LAP-1"
    assert rows["Refresh Rate"].winner_skus == ["LAP-1"]


# -------------------------------------------------------------------------
# 3. Ties: Subset Ties vs All-Way Ties
# -------------------------------------------------------------------------
def test_ties_all_and_subset() -> None:
    """Verify tie resolution: subset ties populate winner_skus, all-way ties leave winner_sku=None and winner_skus=[]."""
    evaluator = MatrixEvaluator()

    p1 = ProductSpec(
        sku="P1",
        name="Device 1",
        brand="BrandA",
        category="Laptops",
        price=1000.0,
        specifications={"ram_gb": 16, "storage_gb": 512},
    )
    p2 = ProductSpec(
        sku="P2",
        name="Device 2",
        brand="BrandB",
        category="Laptops",
        price=1000.0,
        specifications={"ram_gb": 16, "storage_gb": 512},
    )
    p3 = ProductSpec(
        sku="P3",
        name="Device 3",
        brand="BrandC",
        category="Laptops",
        price=1200.0,
        specifications={"ram_gb": 8, "storage_gb": 512},
    )

    matrix = evaluator.evaluate_matrix([p1, p2, p3])
    rows = {r.feature: r for r in matrix}

    # RAM: P1 (16) and P2 (16) tie for first over P3 (8) -> subset tie
    ram_row = rows["Memory (RAM)"]
    assert ram_row.winner_sku is None
    assert set(ram_row.winner_skus) == {"P1", "P2"}

    # Price: P1 ($1000) and P2 ($1000) tie for lower price over P3 ($1200) -> subset tie
    price_row = rows["Price"]
    assert price_row.winner_sku is None
    assert set(price_row.winner_skus) == {"P1", "P2"}

    # Storage: All 3 have 512 GB -> all-way tie -> winner_sku=None and winner_skus=[]
    storage_row = rows["Storage (SSD)"]
    assert storage_row.winner_sku is None
    assert storage_row.winner_skus == []


# -------------------------------------------------------------------------
# 4. Polarity Evaluation across all 5 Categories
# -------------------------------------------------------------------------
def test_polarities_laptops(sample_laptop_1: ProductSpec, sample_laptop_2: ProductSpec) -> None:
    """Verify laptop polarities: RAM, storage, battery higher; weight lower; processor tiers."""
    evaluator = MatrixEvaluator()
    matrix = evaluator.evaluate_matrix([sample_laptop_1, sample_laptop_2])
    rows = {r.feature: r for r in matrix}

    # RAM (32 vs 16): higher wins -> LAP-1
    assert rows["Memory (RAM)"].winner_sku == "LAP-1"
    # Storage (1000 vs 512): higher wins -> LAP-1
    assert rows["Storage (SSD)"].winner_sku == "LAP-1"
    # Battery (18 vs 12): higher wins -> LAP-1
    assert rows["Battery Life"].winner_sku == "LAP-1"
    # Weight (2.8 vs 2.5): lower wins -> LAP-2
    assert rows["Weight"].winner_sku == "LAP-2"
    # Processor (Apple M3 Pro vs Intel Core i5): higher tier wins -> LAP-1
    assert rows["Processor / CPU"].winner_sku == "LAP-1"


def test_polarities_headphones(
    sample_headphones_1: ProductSpec, sample_headphones_2: ProductSpec
) -> None:
    """Verify headphone polarities: driver size, battery, noise canceling higher/True; weight lower."""
    evaluator = MatrixEvaluator()
    matrix = evaluator.evaluate_matrix([sample_headphones_1, sample_headphones_2])
    rows = {r.feature: r for r in matrix}

    # Driver size (40 vs 30 mm): higher wins -> HP-1
    assert rows["Driver Size"].winner_sku == "HP-1"
    # Battery life (30 vs 20 hrs): higher wins -> HP-1
    assert rows["Battery Life"].winner_sku == "HP-1"
    # Noise canceling (True vs False): True wins -> HP-1
    assert rows["Active Noise Canceling"].winner_sku == "HP-1"
    # Weight (8.5 vs 10.2 oz): lower wins -> HP-1
    assert rows["Weight (oz)"].winner_sku == "HP-1"


def test_polarities_smarthome(
    sample_smarthome_1: ProductSpec, sample_smarthome_2: ProductSpec
) -> None:
    """Verify smart home polarities: sensor range higher, sensor included True, battery months higher."""
    evaluator = MatrixEvaluator()
    matrix = evaluator.evaluate_matrix([sample_smarthome_1, sample_smarthome_2])
    rows = {r.feature: r for r in matrix}

    # Sensor range (50 vs 25 ft): higher wins -> SH-1
    assert rows["Sensor Detection Range"].winner_sku == "SH-1"
    # Sensor included (True vs False): True wins -> SH-1
    assert rows["Sensor Included"].winner_sku == "SH-1"
    # Battery life (6 vs 3 months): higher wins -> SH-1
    assert rows["Battery Life (Months)"].winner_sku == "SH-1"


def test_polarities_tvs(sample_tv_1: ProductSpec, sample_tv_2: ProductSpec) -> None:
    """Verify TV polarities: HDMI ports higher, response time lower, resolution pixel count higher, panel tiers."""
    evaluator = MatrixEvaluator()
    matrix = evaluator.evaluate_matrix([sample_tv_1, sample_tv_2])
    rows = {r.feature: r for r in matrix}

    # HDMI ports (4 vs 3): higher wins -> TV-1
    assert rows["Hdmi Ports"].winner_sku == "TV-1"
    # Response time (0.1 vs 4.0 ms): lower wins -> TV-1
    assert rows["Response Time"].winner_sku == "TV-1"
    # Resolution (4K 3840x2160 vs 1920x1080): higher pixel count wins -> TV-1
    assert rows["Display Resolution"].winner_sku == "TV-1"
    # Panel type (OLED evo vs QLED): higher tier wins -> TV-1
    assert rows["Display Panel Type"].winner_sku == "TV-1"


# -------------------------------------------------------------------------
# 5. Synonym Normalization
# -------------------------------------------------------------------------
def test_synonym_normalization(sample_tv_1: ProductSpec, sample_tv_2: ProductSpec) -> None:
    """Verify synonymous keys like panel_type vs display_technology and screen_size_in vs display_size_in normalize to single rows."""
    evaluator = MatrixEvaluator()
    # sample_tv_1 has 'display_technology: OLED evo' and 'screen_size_in: 65.0'
    # sample_tv_2 has 'panel_type: QLED' and 'display_size_in: 55.0'
    matrix = evaluator.evaluate_matrix([sample_tv_1, sample_tv_2])
    features = [r.feature for r in matrix]

    # Must be unified into a single panel type row, not duplicate rows
    panel_rows = [f for f in features if "Panel" in f or "Technology" in f]
    assert len(panel_rows) == 1
    assert panel_rows[0] == "Display Panel Type"

    # Must be unified into a single display size row
    size_rows = [f for f in features if "Size" in f]
    assert len(size_rows) == 1
    assert size_rows[0] == "Display Size"

    # Values must be aligned for both products in the single row
    row_map = {r.feature: r for r in matrix}
    assert row_map["Display Panel Type"].values["TV-1"] == "OLED evo"
    assert row_map["Display Panel Type"].values["TV-2"] == "QLED"
    assert row_map["Display Panel Type"].winner_sku == "TV-1"

    assert row_map["Display Size"].winner_sku == "TV-1"


# -------------------------------------------------------------------------
# 6. Hybrid Router in synthesize_comparison_with_llm
# -------------------------------------------------------------------------
def test_hybrid_router_clean_query_skips_matrix_llm(
    sample_laptop_1: ProductSpec, sample_laptop_2: ProductSpec
) -> None:
    """Verify clean comparison query executes deterministically in 0ms without spawning _run_matrix_winners_llm."""
    orch = ComparisonOrchestrator()
    orch._run_matrix_winners_llm = MagicMock()

    # Mock the narrative LLM call
    mock_resp = MagicMock()
    mock_resp.text = '{"summary": "Direct comparison between laptops [SKU: LAP-1] and [SKU: LAP-2].", "recommendations": "Best overall: [SKU: LAP-1]."}'
    mock_resp.usage_metadata = MagicMock(prompt_token_count=100, candidates_token_count=50)
    orch._call_genai_with_failover = MagicMock(return_value=mock_resp)

    matrix = []
    clean_query = "Compare Apple MacBook Air M3 and Dell XPS 13"
    orch.synthesize_comparison_with_llm(
        [sample_laptop_1, sample_laptop_2],
        matrix,
        query=clean_query,
        model="gemini-2.5-pro",
    )

    # Matrix winners LLM must NOT be called for clean query
    orch._run_matrix_winners_llm.assert_not_called()
    assert len(matrix) > 0
    # Deterministic winners should be populated
    matrix_rows = {r.feature: r for r in matrix}
    assert matrix_rows["Memory (RAM)"].winner_sku == "LAP-1"


def test_hybrid_router_preference_query_invokes_flash_lite(
    sample_laptop_1: ProductSpec, sample_laptop_2: ProductSpec
) -> None:
    """Verify preference query (e.g. for travel/coding) routes to gemini-2.5-flash-lite with <customer_preferences> conditioning."""
    orch = ComparisonOrchestrator()

    mock_resp = MagicMock()
    mock_resp.text = '{"summary": "Direct comparison between laptops [SKU: LAP-1] and [SKU: LAP-2].", "recommendations": "Best for travel: [SKU: LAP-2]."}'
    mock_resp.usage_metadata = MagicMock(prompt_token_count=100, candidates_token_count=50)
    orch._call_genai_with_failover = MagicMock(return_value=mock_resp)

    captured_calls = []

    def mock_run_matrix_winners_llm(
        client, call_model, matrix_prompt, armor_cfg, thinking_cfg, is_mock_env, clean_json_fn
    ):
        captured_calls.append(
            {
                "call_model": call_model,
                "matrix_prompt": matrix_prompt,
            }
        )
        return {"battery_life_hours": "LAP-1", "weight_lbs": "LAP-2"}, 50, 20

    orch._run_matrix_winners_llm = mock_run_matrix_winners_llm

    matrix = []
    pref_query = "Compare Apple MacBook Air M3 and Dell XPS 13 for travel"
    orch.synthesize_comparison_with_llm(
        [sample_laptop_1, sample_laptop_2],
        matrix,
        query=pref_query,
        model="gemini-2.5-pro",
    )

    # Matrix winners LLM MUST be called for preference query
    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert call["call_model"] == "gemini-2.5-flash-lite"
    assert "<customer_preferences>" in call["matrix_prompt"]
    assert "travel" in call["matrix_prompt"]


def test_deterministic_evaluator_never_covers_preferences(
    sample_laptop_1: ProductSpec, sample_laptop_2: ProductSpec
) -> None:
    """Verify that the deterministic evaluator NEVER covers, parses, or reorders based on preferences."""
    evaluator = MatrixEvaluator()

    # Pure deterministic baseline (no query)
    matrix_pure = evaluator.evaluate_matrix([sample_laptop_1, sample_laptop_2])

    # Query with strong preference keywords (e.g. gaming, travel, office)
    matrix_gaming = evaluator.evaluate_matrix(
        [sample_laptop_1, sample_laptop_2], query="best laptop for gaming and esports"
    )
    matrix_travel = evaluator.evaluate_matrix(
        [sample_laptop_1, sample_laptop_2], query="best lightweight laptop for travel"
    )

    # Features and winners must be 100% identical in order and result:
    assert [r.feature for r in matrix_pure] == [r.feature for r in matrix_gaming]
    assert [r.feature for r in matrix_pure] == [r.feature for r in matrix_travel]
    for r_pure, r_gaming, r_travel in zip(matrix_pure, matrix_gaming, matrix_travel, strict=True):
        assert r_pure.winner_sku == r_gaming.winner_sku == r_travel.winner_sku
        assert r_pure.winner_skus == r_gaming.winner_skus == r_travel.winner_skus


# -------------------------------------------------------------------------
# 7. Helper Function & Edge Case Unit Tests
# -------------------------------------------------------------------------
def test_parse_resolution_pixels() -> None:
    """Test resolution parser across dimensions, shorthand tokens, and edge cases."""
    assert parse_resolution_pixels(None) is None
    assert parse_resolution_pixels("3840 x 2160") == 3840 * 2160
    assert parse_resolution_pixels("2560x1600") == 2560 * 1600
    assert parse_resolution_pixels("8k ultra hd") == 7680 * 4320
    assert parse_resolution_pixels("4K UHD") == 3840 * 2160
    assert parse_resolution_pixels("QHD 1440p") == 2560 * 1440
    assert parse_resolution_pixels("FHD 1080p") == 1920 * 1080
    assert parse_resolution_pixels("720p HD") == 1280 * 720
    assert parse_resolution_pixels("Liquid Retina display") == 2560 * 1600
    assert parse_resolution_pixels("Unknown format") is None


def test_score_panel_tier() -> None:
    """Test panel tier scoring across tiers 5 down to 0 and fallbacks."""
    assert score_panel_tier(None) is None
    assert score_panel_tier("") is None
    assert score_panel_tier("Tandem OLED") == 5
    assert score_panel_tier("QD-OLED") == 5
    assert score_panel_tier("OLED evo") == 5
    assert score_panel_tier("Dynamic AMOLED 2X") == 4
    assert score_panel_tier("Super AMOLED") == 4
    assert score_panel_tier("Mini-LED Liquid Retina XDR") == 3
    assert score_panel_tier("QLED Quantum Dot") == 2
    assert score_panel_tier("IPS LED") == 1
    assert score_panel_tier("TN Film") == 0
    assert score_panel_tier("VA Panel") == 0
    assert score_panel_tier("Unknown Custom Tech") == 1


def test_score_processor_tier() -> None:
    """Test processor tier scoring across tiers 7 down to 1 and fallbacks."""
    assert score_processor_tier(None) is None
    assert score_processor_tier("") is None
    assert score_processor_tier("Apple M4 Max") == 7
    assert score_processor_tier("Intel Core Ultra 9 185H") == 7
    assert score_processor_tier("Intel Core i9-14900HX") == 7
    assert score_processor_tier("Apple M3 Pro") == 6
    assert score_processor_tier("Intel Core Ultra 7 155H") == 6
    assert score_processor_tier("AMD Ryzen 7 7840HS") == 6
    assert score_processor_tier("Apple M3") == 5
    assert score_processor_tier("Intel Core Ultra 5 125H") == 5
    assert score_processor_tier("Snapdragon X Elite") == 5
    assert score_processor_tier("Apple M1") == 4
    assert score_processor_tier("Intel Core i3-1215U") == 4
    assert score_processor_tier("Snapdragon X Plus") == 4
    assert score_processor_tier("Snapdragon 8cx Gen 3") == 3
    assert score_processor_tier("Intel Celeron N4020") == 2
    assert score_processor_tier("Intel Pentium Gold") == 2
    assert score_processor_tier("AMD A10-9700") == 1
    assert score_processor_tier("Unrecognized Chipset") == 3


def test_parse_boolean() -> None:
    """Test boolean parser across bools, strings, and descriptive phrases."""
    assert parse_boolean(None) is None
    assert parse_boolean(True) is True
    assert parse_boolean(False) is False
    assert parse_boolean("yes") is True
    assert parse_boolean("true") is True
    assert parse_boolean("1") is True
    assert parse_boolean("included") is True
    assert parse_boolean("active") is True
    assert parse_boolean("adaptive") is True
    assert parse_boolean("no") is False
    assert parse_boolean("false") is False
    assert parse_boolean("0") is False
    assert parse_boolean("none") is False
    assert parse_boolean("not included") is False
    assert parse_boolean("Active Noise Canceling with Transparency") is True
    assert parse_boolean("standard passive stereo") is None


def test_format_spec_value_and_labels() -> None:
    """Test format_spec_value across units, lists, booleans, and custom labels."""
    assert format_spec_value("storage_gb", None) == "Not specified"
    assert format_spec_value("storage_gb", 512) == "512 GB"
    assert format_spec_value("storage_gb", 1000) == "1 TB"
    assert format_spec_value("battery_life_hours", 18) == "Up to 18 hours"
    assert format_spec_value("noise_canceling", True) == "Yes"
    assert format_spec_value("noise_canceling", False) == "No"
    assert format_spec_value("screen_size_in", 15.6) == '15.6"'
    assert format_spec_value("refresh_rate_hz", 144) == "144 Hz"
    assert format_spec_value("weight_lbs", 3.2) == "3.2 lbs"
    assert format_spec_value("weight_oz", 8.5) == "8.5 oz"
    assert format_spec_value("driver_size_mm", 40) == "40 mm"
    assert format_spec_value("sensor_range_ft", 30) == "30 ft"
    assert format_spec_value("response_time_ms", 1.0) == "1.0 ms"
    assert format_spec_value("features", ["Bluetooth 5.3", "WiFi 6E"]) == "Bluetooth 5.3, WiFi 6E"
    assert format_spec_value("custom_untyped", "Val") == "Val"

    assert format_spec_label("ram_gb") == "Memory (RAM)"
    assert format_spec_label("display_technology") == "Display Panel Type"
    assert format_spec_label("some_unknown_feature") == "Some Unknown Feature"
    assert normalize_spec_key("screen_size_in") == "display_size_in"


def test_extract_numeric() -> None:
    """Test extract_numeric across ints, floats, strings, and non-numeric values."""
    assert extract_numeric(None) is None
    assert extract_numeric(16) == 16.0
    assert extract_numeric(16.5) == 16.5
    assert extract_numeric("16 GB") == 16.0
    assert extract_numeric("2.8 lbs") == 2.8
    assert extract_numeric("no numeric content here") is None


def test_edge_cases_empty_and_single_product(sample_laptop_1: ProductSpec) -> None:
    """Test evaluator edge cases: empty product list and single product comparison."""
    evaluator = MatrixEvaluator()
    assert evaluator.evaluate_matrix([]) == []

    # Single product evaluation
    single_matrix = evaluator.evaluate_matrix([sample_laptop_1])
    assert len(single_matrix) > 0
    # For single product, verify all rows contain the product's values
    for row in single_matrix:
        assert "LAP-1" in row.values


def test_product_spec_raw_with_no_specifications() -> None:
    """Test get_product_spec_raw when product has None specifications."""
    mock_p = MagicMock()
    mock_p.specifications = None
    val = MatrixEvaluator.get_product_spec_raw(mock_p, "ram_gb")
    assert val is None
