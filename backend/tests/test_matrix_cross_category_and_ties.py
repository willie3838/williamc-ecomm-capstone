"""Unit tests verifying cross-category spec winners and multi-winner ties in the comparison matrix."""

from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import ProductSpec


def test_cross_category_shared_specs_produce_winner() -> None:
    """Verify shared numeric specs across different categories compute winners (e.g. Laptop vs Tablet)."""
    orch = ComparisonOrchestrator(hermetic=True)
    laptop = ProductSpec(
        sku="LAP-101",
        name="Ultra Laptop 14",
        brand="Dell",
        category="Laptops",
        price=1199.99,
        specifications={
            "storage_gb": 512,
            "ram_gb": 16,
            "battery_life_hours": 15,
            "refresh_rate_hz": 120,
            "weight_lbs": 2.8,
            "display_size_in": 14.0,
        },
    )
    tablet = ProductSpec(
        sku="TAB-202",
        name="Pro Tablet 11",
        brand="Apple",
        category="Tablets",
        price=799.99,
        specifications={
            "storage_gb": 256,
            "ram_gb": 8,
            "battery_life_hours": 10,
            "refresh_rate_hz": 60,
            "weight_lbs": 1.1,
            "display_size_in": 11.0,
        },
    )

    matrix = orch.build_comparison_matrix([laptop, tablet])
    rows = {r.feature: r for r in matrix}

    # Category row present and neutral
    assert "Category" in rows
    assert rows["Category"].winner_sku is None
    assert rows["Category"].winner_skus == []

    # Price winner is cheaper tablet
    assert rows["Price"].winner_sku == "TAB-202"
    assert rows["Price"].winner_skus == ["TAB-202"]

    # Storage (512 vs 256): higher wins -> laptop
    assert rows["Storage (SSD)"].winner_sku == "LAP-101"
    assert rows["Storage (SSD)"].winner_skus == ["LAP-101"]

    # RAM (16 vs 8): higher wins -> laptop
    assert rows["Memory (RAM)"].winner_sku == "LAP-101"
    assert rows["Memory (RAM)"].winner_skus == ["LAP-101"]

    # Battery Life (15 vs 10): higher wins -> laptop
    assert rows["Battery Life"].winner_sku == "LAP-101"
    assert rows["Battery Life"].winner_skus == ["LAP-101"]

    # Refresh Rate (120 vs 60): higher wins -> laptop
    assert rows["Refresh Rate"].winner_sku == "LAP-101"
    assert rows["Refresh Rate"].winner_skus == ["LAP-101"]

    # Weight (2.8 vs 1.1): lower wins -> tablet
    assert rows["Weight"].winner_sku == "TAB-202"
    assert rows["Weight"].winner_skus == ["TAB-202"]

    # Display Size (14.0 vs 11.0): higher wins -> laptop
    assert rows["Display Size"].winner_sku == "LAP-101"
    assert rows["Display Size"].winner_skus == ["LAP-101"]


def test_cross_category_unshared_specs_remain_neutral() -> None:
    """Verify specs present on only a subset of products leave winner_sku=None and winner_skus=[]."""
    orch = ComparisonOrchestrator(hermetic=True)
    laptop = ProductSpec(
        sku="LAP-102",
        name="Gaming Laptop 16",
        brand="Asus",
        category="Laptops",
        price=1499.99,
        specifications={
            "storage_gb": 1000,
            "gpu": "RTX 4070",
            "processor": "Intel Core i7",
        },
    )
    tablet = ProductSpec(
        sku="TAB-203",
        name="Budget Tablet",
        brand="Lenovo",
        category="Tablets",
        price=249.99,
        specifications={
            "storage_gb": 128,
            "stylus_included": True,
        },
    )

    matrix = orch.build_comparison_matrix([laptop, tablet])
    rows = {r.feature: r for r in matrix}

    # Shared spec has a winner
    assert rows["Storage (SSD)"].winner_sku == "LAP-102"
    assert rows["Storage (SSD)"].winner_skus == ["LAP-102"]

    # Unshared specs have no winner
    assert rows["Gpu"].winner_sku is None
    assert rows["Gpu"].winner_skus == []
    assert rows["Processor / CPU"].winner_sku is None
    assert rows["Processor / CPU"].winner_skus == []
    assert rows["Stylus Included"].winner_sku is None
    assert rows["Stylus Included"].winner_skus == []


def test_three_way_comparison_two_way_tie_winner_skus() -> None:
    """Verify 3+ product comparisons with a 2-way tie populate winner_skus and winner_sku=None."""
    orch = ComparisonOrchestrator(hermetic=True)
    p1 = ProductSpec(
        sku="SKU-A",
        name="Laptop Alpha",
        brand="BrandA",
        category="Laptops",
        price=999.99,
        rating=4.5,
        specifications={"refresh_rate_hz": 120, "ram_gb": 16, "storage_gb": 512},
    )
    p2 = ProductSpec(
        sku="SKU-B",
        name="Laptop Beta",
        brand="BrandB",
        category="Laptops",
        price=999.99,
        rating=4.8,
        specifications={"refresh_rate_hz": 120, "ram_gb": 16, "storage_gb": 256},
    )
    p3 = ProductSpec(
        sku="SKU-C",
        name="Laptop Gamma",
        brand="BrandC",
        category="Laptops",
        price=1299.99,
        rating=4.8,
        specifications={"refresh_rate_hz": 60, "ram_gb": 8, "storage_gb": 512},
    )

    matrix = orch.build_comparison_matrix([p1, p2, p3])
    rows = {r.feature: r for r in matrix}

    # Price: SKU-A and SKU-B tie at $999.99 beating SKU-C at $1299.99
    assert rows["Price"].winner_sku is None
    assert set(rows["Price"].winner_skus) == {"SKU-A", "SKU-B"}

    # Rating: SKU-B and SKU-C tie at 4.8 beating SKU-A at 4.5
    assert rows["Customer Rating"].winner_sku is None
    assert set(rows["Customer Rating"].winner_skus) == {"SKU-B", "SKU-C"}

    # Refresh Rate: SKU-A and SKU-B tie at 120Hz beating SKU-C at 60Hz
    assert rows["Refresh Rate"].winner_sku is None
    assert set(rows["Refresh Rate"].winner_skus) == {"SKU-A", "SKU-B"}

    # RAM: SKU-A and SKU-B tie at 16GB beating SKU-C at 8GB
    assert rows["Memory (RAM)"].winner_sku is None
    assert set(rows["Memory (RAM)"].winner_skus) == {"SKU-A", "SKU-B"}

    # Storage: SKU-A and SKU-C tie at 512GB beating SKU-B at 256GB
    assert rows["Storage (SSD)"].winner_sku is None
    assert set(rows["Storage (SSD)"].winner_skus) == {"SKU-A", "SKU-C"}


def test_three_way_comparison_all_tie_neutral() -> None:
    """Verify when all products tie for a spec, row is neutral (winner_sku=None, winner_skus=[])."""
    orch = ComparisonOrchestrator(hermetic=True)
    p1 = ProductSpec(
        sku="SKU-1",
        name="Phone A",
        brand="Brand",
        category="Phones",
        price=799.00,
        rating=4.5,
        specifications={"refresh_rate_hz": 120},
    )
    p2 = ProductSpec(
        sku="SKU-2",
        name="Phone B",
        brand="Brand",
        category="Phones",
        price=799.00,
        rating=4.5,
        specifications={"refresh_rate_hz": 120},
    )
    p3 = ProductSpec(
        sku="SKU-3",
        name="Phone C",
        brand="Brand",
        category="Phones",
        price=799.00,
        rating=4.5,
        specifications={"refresh_rate_hz": 120},
    )

    matrix = orch.build_comparison_matrix([p1, p2, p3])
    rows = {r.feature: r for r in matrix}

    # All tie on price -> neutral
    assert rows["Price"].winner_sku is None
    assert rows["Price"].winner_skus == []

    # All tie on rating -> neutral
    assert rows["Customer Rating"].winner_sku is None
    assert rows["Customer Rating"].winner_skus == []

    # All tie on refresh rate -> neutral
    assert rows["Refresh Rate"].winner_sku is None
    assert rows["Refresh Rate"].winner_skus == []


def test_single_winner_compatibility() -> None:
    """Verify single winner populates both winner_sku and winner_skus=[winner_sku]."""
    orch = ComparisonOrchestrator(hermetic=True)
    p1 = ProductSpec(
        sku="SKU-1",
        name="Laptop 1",
        brand="B1",
        category="Laptops",
        price=800.0,
        specifications={"ram_gb": 32},
    )
    p2 = ProductSpec(
        sku="SKU-2",
        name="Laptop 2",
        brand="B2",
        category="Laptops",
        price=1000.0,
        specifications={"ram_gb": 16},
    )

    matrix = orch.build_comparison_matrix([p1, p2])
    rows = {r.feature: r for r in matrix}

    assert rows["Price"].winner_sku == "SKU-1"
    assert rows["Price"].winner_skus == ["SKU-1"]

    assert rows["Memory (RAM)"].winner_sku == "SKU-1"
    assert rows["Memory (RAM)"].winner_skus == ["SKU-1"]
