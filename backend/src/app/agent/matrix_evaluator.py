"""Deterministic Greater-Set Comparison Matrix Evaluator.

Evaluates technical specifications across the union of non-warehouse specs for 2 to 5 products:
- Missing specs automatically lose to products with valid spec values.
- Evaluates polarities:
  * Higher is better: RAM, storage, battery, display size, HDMI ports, driver size, sensor range, refresh rate, rating.
  * Lower is better: price, weight, response time.
  * Boolean True is better: noise canceling, sensor included, stylus included.
  * Resolution pixel count: higher is better.
  * Display panel tiers and processor tiers.
  * Normalizing synonymous keys like panel_type vs display_technology, screen_size_in vs display_size_in.
"""

import re
from typing import Any

from app.models.responses import MatrixRow, ProductSpec

NON_COMPARATIVE_SPEC_KEYS: frozenset[str] = frozenset(
    {
        "upc",
        "model_number",
        "product_type",
        "subcategory",
        "taxonomy_path",
        "warranty",
        "shipping_tier",
    }
)

SYNONYMOUS_SPEC_KEYS: dict[str, str] = {
    "display_technology": "panel_type",
    "screen_size_in": "display_size_in",
    "noise_cancellation": "noise_canceling",
    "resolution": "display_resolution",
}

CANONICAL_SYNONYMS: dict[str, list[str]] = {
    "panel_type": ["display_technology"],
    "display_size_in": ["screen_size_in"],
    "noise_canceling": ["noise_cancellation"],
    "display_resolution": ["resolution"],
}

SPEC_LABELS: dict[str, str] = {
    "processor": "Processor / CPU",
    "ram_gb": "Memory (RAM)",
    "storage_gb": "Storage (SSD)",
    "battery_life_hours": "Battery Life",
    "battery_life_months": "Battery Life (Months)",
    "display_size_in": "Display Size",
    "screen_size_in": "Screen Size",
    "display_resolution": "Display Resolution",
    "refresh_rate_hz": "Refresh Rate",
    "weight_lbs": "Weight",
    "weight_oz": "Weight (oz)",
    "bluetooth_version": "Bluetooth Version",
    "ports": "Ports & Connectivity",
    "driver_size_mm": "Driver Size",
    "noise_canceling": "Active Noise Canceling",
    "noise_cancellation": "Active Noise Canceling",
    "sensor_range_ft": "Sensor Detection Range",
    "response_time_ms": "Response Time",
    "panel_type": "Display Panel Type",
    "display_technology": "Display Panel Type",
    "hdr_support": "HDR Format Support",
    "smart_platform": "Smart Platform / Ecosystem",
    "connectivity": "Wireless Connectivity",
    "voice_assistant": "Voice Assistant",
    "sensor_included": "Sensor Included",
    "stylus_included": "Stylus Included",
    "gpu": "Gpu",
    "hdmi_ports": "Hdmi Ports",
}

HIGHER_IS_BETTER_KEYS: frozenset[str] = frozenset(
    {
        "ram_gb",
        "storage_gb",
        "battery_life_hours",
        "battery_life_months",
        "display_size_in",
        "screen_size_in",
        "driver_size_mm",
        "sensor_range_ft",
        "refresh_rate_hz",
        "hdmi_ports",
        "rating",
    }
)

LOWER_IS_BETTER_KEYS: frozenset[str] = frozenset(
    {
        "price",
        "weight_lbs",
        "weight_oz",
        "response_time_ms",
    }
)

BOOLEAN_KEYS: frozenset[str] = frozenset(
    {
        "noise_canceling",
        "noise_cancellation",
        "sensor_included",
        "stylus_included",
        "multipoint_pairing",
        "quick_charge",
    }
)


def normalize_spec_key(key: str) -> str:
    """Normalize a raw specification key to its canonical form."""
    k = str(key).strip().lower()
    return SYNONYMOUS_SPEC_KEYS.get(k, k)


def format_spec_label(spec_key: str) -> str:
    """Format a specification key into a human-readable matrix feature label."""
    norm_key = normalize_spec_key(spec_key)
    if norm_key in SPEC_LABELS:
        return SPEC_LABELS[norm_key]
    if spec_key in SPEC_LABELS:
        return SPEC_LABELS[spec_key]
    return spec_key.replace("_", " ").title()


def format_spec_value(spec_key: str, raw_val: Any) -> str:
    """Format a raw specification value with appropriate human-readable units."""
    if raw_val is None:
        return "Not specified"
    norm_key = normalize_spec_key(spec_key)
    if norm_key == "storage_gb" and isinstance(raw_val, (int, float)):
        return f"{raw_val} GB" if raw_val < 1000 else f"{raw_val / 1000:g} TB"
    if norm_key == "battery_life_hours" and isinstance(raw_val, (int, float)):
        return f"Up to {raw_val} hours"
    if isinstance(raw_val, bool):
        return "Yes" if raw_val else "No"
    if isinstance(raw_val, (int, float)):
        suffix_units = (
            ("_gb", " GB"),
            ("_months", " months"),
            ("_in", '"'),
            ("_hz", " Hz"),
            ("_lbs", " lbs"),
            ("_oz", " oz"),
            ("_mm", " mm"),
            ("_ft", " ft"),
            ("_ms", " ms"),
            ("_db", " dB"),
            ("_nits", " nits"),
            ("_w", " W"),
        )
        for suffix, unit in suffix_units:
            if norm_key.endswith(suffix) or spec_key.endswith(suffix):
                return f"{raw_val}{unit}"
        return str(raw_val)
    if isinstance(raw_val, list):
        return ", ".join(str(item) for item in raw_val)
    return str(raw_val)


def extract_numeric(val: Any) -> float | None:
    """Extract a numeric float value from a number or string."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Look for leading/standalone numbers e.g. "16 GB", "2.8 lbs", "0.1 ms"
        m = re.search(r"[-+]?\d*\.?\d+", val)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def parse_resolution_pixels(val: Any) -> int | None:
    """Parse screen resolution string into total pixel count (width * height)."""
    if val is None:
        return None
    text = str(val).lower()
    # Match width x height (e.g., 3840 x 2160, 2560x1664, 1920 X 1080)
    match = re.search(r"(\d{3,5})\s*[x×X]\s*(\d{3,5})", text)
    if match:
        try:
            return int(match.group(1)) * int(match.group(2))
        except (ValueError, OverflowError):
            pass
    if "8k" in text:
        return 7680 * 4320
    if "4k" in text:
        return 3840 * 2160
    if "qhd" in text or "1440p" in text:
        return 2560 * 1440
    if "fhd" in text or "1080p" in text:
        return 1920 * 1080
    if "720p" in text or "hd" in text:
        return 1280 * 720
    if "retina" in text:
        return 2560 * 1600
    return None


def score_panel_tier(val: Any) -> int | None:
    """Score display panel technology on a progressive quality tier scale (0-5)."""
    if not val:
        return None
    text = str(val).lower()
    # Tier 5: Cutting-edge / Tandem OLED / MLA / QD-OLED / OLED evo
    if any(
        kw in text
        for kw in (
            "tandem oled",
            "qd-oled",
            "oled evo",
            "mla",
            "master mla",
        )
    ):
        return 5
    # Tier 4: OLED / AMOLED / Dynamic AMOLED
    if any(
        kw in text
        for kw in (
            "oled",
            "dynamic amoled",
            "super amoled",
            "amoled",
        )
    ):
        return 4
    # Tier 3: Mini-LED / Liquid Retina XDR
    if any(
        kw in text
        for kw in (
            "liquid retina xdr",
            "mini-led",
            "qd-mini led",
            "mini led",
        )
    ):
        return 3
    # Tier 2: QLED / ULED / NanoCell
    if any(
        kw in text
        for kw in (
            "qled",
            "uled",
            "nanocell",
            "triluminos",
        )
    ):
        return 2
    # Tier 1: IPS / Liquid Retina / standard LED LCD
    if any(
        kw in text
        for kw in (
            "liquid retina",
            "ips",
            "led",
            "lcd",
        )
    ):
        return 1
    # Tier 0: TN / TFT
    if any(kw in text for kw in ("tn", "tft", "va")):
        return 0
    return 1


def score_processor_tier(val: Any) -> int | None:
    """Score processor capability on a progressive tier scale (1-7)."""
    if not val:
        return None
    text = str(val).lower()
    # Tier 7: Extreme Enthusiast / Workstation
    if any(
        kw in text
        for kw in (
            "m4 max",
            "m3 max",
            "core ultra 9",
            "ryzen 9",
            "intel core i9",
            "i9-",
        )
    ):
        return 7
    # Tier 6: High Performance / Pro
    if any(
        kw in text
        for kw in (
            "m4 pro",
            "m3 pro",
            "m2 max",
            "core ultra 7",
            "ryzen 7",
            "intel core i7",
            "i7-",
        )
    ):
        return 6
    # Tier 5: Balanced Performance / Mainstream High
    if any(
        kw in text
        for kw in (
            "apple m4",
            "m4 chip",
            "apple m3",
            "m3 chip",
            "apple m2",
            "m2 pro",
            "core ultra 5",
            "ryzen 5",
            "intel core i5",
            "i5-",
            "snapdragon x elite",
        )
    ):
        return 5
    # Tier 4: Mainstream Standard
    if any(
        kw in text
        for kw in (
            "apple m1",
            "m1 chip",
            "core ultra 3",
            "snapdragon x plus",
            "intel core i3",
            "i3-",
            "ryzen 3",
        )
    ):
        return 4
    # Tier 3: Entry / Efficient
    if any(
        kw in text
        for kw in (
            "snapdragon 8cx",
            "snapdragon 7c",
            "snapdragon 4c",
            "snapdragon",
        )
    ):
        return 3
    # Tier 2: Budget / Basic
    if any(kw in text for kw in ("pentium", "celeron")):
        return 2
    # Tier 1: Legacy Entry
    if any(
        kw in text
        for kw in (
            "amd a10",
            "amd a8",
            "amd a6",
            "amd a4",
            "a10",
            "a8",
            "a6",
            "a4",
        )
    ):
        return 1
    return 3


def parse_boolean(val: Any) -> bool | None:
    """Parse a boolean value or boolean-equivalent string."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    text = str(val).strip().lower()
    if text in ("true", "yes", "1", "included", "active", "adaptive"):
        return True
    if text in ("false", "no", "0", "none", "not included"):
        return False
    # If a descriptive text like "Active Noise Canceling with Auto NC Optimizer" -> True
    if any(kw in text for kw in ("noise cancel", "anc", "included", "adaptive")):
        return True
    return None


class MatrixEvaluator:
    """Deterministic matrix builder and spec winner evaluator for catalog comparisons."""

    @classmethod
    def get_product_spec_raw(cls, product: ProductSpec, canonical_key: str) -> Any:
        """Retrieve a specification value for a product, checking canonical and synonymous keys."""
        if not product.specifications:
            return None
        val = product.specifications.get(canonical_key)
        if val is not None:
            return val
        alts = CANONICAL_SYNONYMS.get(canonical_key, [])
        for alt in alts:
            alt_val = product.specifications.get(alt)
            if alt_val is not None:
                return alt_val
        return None

    @classmethod
    def collect_greater_spec_keys(cls, products: list[ProductSpec]) -> list[str]:
        """Collect the ordered union of all non-warehouse comparative specification keys across products."""
        seen: set[str] = set()
        canonical_keys: list[str] = []
        for p in products:
            if not p.specifications:
                continue
            for k in p.specifications.keys():
                norm = normalize_spec_key(k)
                if norm in NON_COMPARATIVE_SPEC_KEYS:
                    continue
                if norm not in seen:
                    seen.add(norm)
                    canonical_keys.append(norm)
        return canonical_keys

    @classmethod
    def evaluate_spec_winner(
        cls,
        spec_key: str,
        products: list[ProductSpec],
    ) -> tuple[str | None, list[str]]:
        """Evaluate deterministic winner(s) for a single spec across 2 to 5 products.

        Rule:
        - Products with missing specs automatically lose to products with valid specs.
        - Higher is better: RAM, storage, battery, display size, HDMI ports, driver size, sensor range, refresh rate.
        - Lower is better: weight, response time.
        - Boolean True is better: noise canceling, sensor included, stylus included.
        - Resolution pixel count: higher is better.
        - Panel and processor tiers: higher tier is better.
        - Subset ties populate winner_skus (winner_sku=None).
        - All-way ties leave winner_sku=None and winner_skus=[].
        """
        if not products or len(products) < 2:
            return (products[0].sku if products else None), ([products[0].sku] if products else [])

        norm_key = normalize_spec_key(spec_key)

        # 1. Gather raw values and filter valid products
        val_map: dict[str, Any] = {p.sku: cls.get_product_spec_raw(p, norm_key) for p in products}

        valid_products: list[ProductSpec] = [
            p
            for p in products
            if val_map[p.sku] is not None
            and str(val_map[p.sku]).strip().lower() not in ("", "none", "not specified", "n/a")
        ]

        # If all products miss the spec -> no winner
        if not valid_products:
            return None, []

        # If only 1 product has the spec, it automatically wins (missing spec loses!)
        if len(valid_products) == 1:
            win_sku = valid_products[0].sku
            return win_sku, [win_sku]

        # 2. Evaluate comparative scores among valid products
        scores: dict[str, float] = {}

        if norm_key in BOOLEAN_KEYS:
            for p in valid_products:
                b = parse_boolean(val_map[p.sku])
                scores[p.sku] = 1.0 if b is True else 0.0
            is_lower_better = False

        elif norm_key == "display_resolution":
            for p in valid_products:
                px = parse_resolution_pixels(val_map[p.sku])
                scores[p.sku] = float(px) if px is not None else 0.0
            is_lower_better = False

        elif norm_key == "panel_type":
            for p in valid_products:
                tier = score_panel_tier(val_map[p.sku])
                scores[p.sku] = float(tier) if tier is not None else 1.0
            is_lower_better = False

        elif norm_key == "processor":
            for p in valid_products:
                tier = score_processor_tier(val_map[p.sku])
                scores[p.sku] = float(tier) if tier is not None else 3.0
            is_lower_better = False

        elif norm_key in LOWER_IS_BETTER_KEYS:
            for p in valid_products:
                num = extract_numeric(val_map[p.sku])
                scores[p.sku] = num if num is not None else float("inf")
            is_lower_better = True

        elif norm_key in HIGHER_IS_BETTER_KEYS:
            for p in valid_products:
                num = extract_numeric(val_map[p.sku])
                scores[p.sku] = num if num is not None else -float("inf")
            is_lower_better = False

        else:
            # Fallback for other attributes (e.g. bluetooth version, gpu, ports)
            # Try numeric extraction first
            nums = {p.sku: extract_numeric(val_map[p.sku]) for p in valid_products}
            if all(v is not None for v in nums.values()):
                scores = {sku: val for sku, val in nums.items() if val is not None}
                is_lower_better = False
            else:
                # Qualitative fallback: distinct non-empty values
                raw_strings = {p.sku: str(val_map[p.sku]).strip().lower() for p in valid_products}
                if len(set(raw_strings.values())) == 1:
                    # All present products have identical string -> tie among present
                    scores = {p.sku: 1.0 for p in valid_products}
                else:
                    # If multiple distinct strings without numeric ordering, treat as tied
                    scores = {p.sku: 1.0 for p in valid_products}
                is_lower_better = False

        # 3. Determine winning score
        valid_scores = [s for s in scores.values() if s not in (float("inf"), -float("inf"))]
        if not valid_scores:
            return None, []

        target_score = min(valid_scores) if is_lower_better else max(valid_scores)
        tied_skus = [p.sku for p in valid_products if scores.get(p.sku) == target_score]

        # If all products in the entire comparison tied:
        if len(tied_skus) == len(products):
            return None, []

        # If exactly 1 winner:
        if len(tied_skus) == 1:
            return tied_skus[0], [tied_skus[0]]

        # Subset tie:
        return None, tied_skus

    def evaluate_matrix(
        self,
        products: list[ProductSpec],
        query: str = "",
        spec_winners: dict[str, str] | None = None,
    ) -> list[MatrixRow]:
        """Build the complete comparison matrix across the greater set of non-warehouse specs.

        The deterministic path evaluates strictly objective, intrinsic product specifications.
        It never parses, infers, or covers user preferences or query keywords.
        """
        if not products:
            return []

        rows: list[MatrixRow] = []

        # Detect cross-category comparison
        distinct_categories = {
            (p.category or "").strip().lower() for p in products if (p.category or "").strip()
        }
        if len(distinct_categories) > 1:
            rows.append(
                MatrixRow(
                    feature="Category",
                    values={p.sku: (p.category or "General") for p in products},
                    winner_sku=None,
                    winner_skus=[],
                )
            )

        # 1. Price comparison (lower is better)
        price_values = {p.sku: f"${p.price:,.2f}" for p in products}
        min_price = min(p.price for p in products)
        price_winners = [p.sku for p in products if p.price == min_price]
        price_winner_skus = price_winners if 0 < len(price_winners) < len(products) else []
        rows.append(
            MatrixRow(
                feature="Price",
                values=price_values,
                winner_sku=price_winners[0] if len(price_winners) == 1 else None,
                winner_skus=price_winner_skus,
            )
        )

        # 2. Rating comparison (higher is better)
        rating_values = {
            p.sku: f"{p.rating:.1f} ★ ({p.review_count or 0})" if p.rating else "N/A"
            for p in products
        }
        valid_ratings = [(p.sku, p.rating) for p in products if p.rating is not None]
        rating_winner = None
        rating_winners: list[str] = []
        if valid_ratings:
            best_rating = max(r[1] for r in valid_ratings)
            top_raters = [r[0] for r in valid_ratings if r[1] == best_rating]
            if 0 < len(top_raters) < len(products):
                rating_winners = top_raters
                if len(top_raters) == 1:
                    rating_winner = top_raters[0]
        rows.append(
            MatrixRow(
                feature="Customer Rating",
                values=rating_values,
                winner_sku=rating_winner,
                winner_skus=rating_winners,
            )
        )

        # 3. Greater set of comparative specifications
        greater_spec_keys = self.collect_greater_spec_keys(products)

        # Normalization for spec_winners overrides
        normalized_overrides: dict[str, str] = {}
        if isinstance(spec_winners, dict):
            for k, v in spec_winners.items():
                if k and v is not None:
                    str_k = str(k).strip()
                    normalized_overrides[str_k] = str(v).strip()
                    normalized_overrides[str_k.lower()] = str(v).strip()
                    normalized_overrides[normalize_spec_key(str_k)] = str(v).strip()

        alias_to_sku: dict[str, str] = {}
        for idx, p in enumerate(products):
            alias_to_sku[f"product_{idx + 1}"] = p.sku
            alias_to_sku[f"product_{chr(ord('a') + idx)}"] = p.sku

        for spec_key in greater_spec_keys:
            label = format_spec_label(spec_key)
            val_map = {
                p.sku: format_spec_value(spec_key, self.get_product_spec_raw(p, spec_key))
                for p in products
            }

            # Check override from spec_winners
            override_raw = (
                normalized_overrides.get(spec_key)
                or normalized_overrides.get(spec_key.lower())
                or normalized_overrides.get(label.lower())
                or normalized_overrides.get(label)
            )

            if override_raw is not None:
                ow_low = override_raw.lower().strip()
                if ow_low in ("tie", "equal", "none", "n/a", ""):
                    winner_sku = None
                    winner_skus = []
                else:
                    matched_skus: list[str] = []
                    if ow_low in alias_to_sku:
                        matched_skus.append(alias_to_sku[ow_low])
                    else:
                        for p in products:
                            if p.sku and p.sku in override_raw and p.sku not in matched_skus:
                                matched_skus.append(p.sku)
                    if 0 < len(matched_skus) < len(products):
                        winner_skus = matched_skus
                        winner_sku = matched_skus[0] if len(matched_skus) == 1 else None
                    else:
                        winner_sku = None
                        winner_skus = []
            else:
                # Default deterministic polarity evaluation
                winner_sku, winner_skus = self.evaluate_spec_winner(spec_key, products)

            rows.append(
                MatrixRow(
                    feature=label,
                    values=val_map,
                    winner_sku=winner_sku,
                    winner_skus=winner_skus,
                )
            )

        return rows
