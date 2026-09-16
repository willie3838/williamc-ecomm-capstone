"""Google ADK comparison orchestrator agent and synthesis pipeline."""

import logging
import re
from typing import Any

from google.adk.agents import Agent
from google.cloud import bigquery

from app.agent.prompts import SYSTEM_INSTRUCTION
from app.config import settings
from app.models.responses import Citation, CompareResponse, MatrixRow, ProductSpec
from app.observability.tracing import get_current_trace_id, get_tracer
from app.tools.catalog import query_catalog

logger = logging.getLogger(__name__)

# Core ADK Root Agent definition
catalog_agent = Agent(
    name="catalog_comparison_orchestrator",
    model=settings.gemini_model,
    instruction=SYSTEM_INSTRUCTION,
    tools=[query_catalog],
)


class ComparisonOrchestrator:
    """Orchestrator for managing catalog comparison workflows and grounded synthesis."""

    def __init__(self, bq_client: bigquery.Client | None = None) -> None:
        self.bq_client = bq_client

    def extract_keywords(self, query: str) -> list[str]:
        """Parse natural language query into target candidate keywords."""
        brand_or_model = r"\b(?:macbook|dell|xps|lenovo|thinkpad|ipad|samsung|galaxy|pixel|tablet|sony|wh-1000|bose|quietcomfort|airpods|nest|ecobee|lg|s90c|c3|oled|thermostat|headphones|laptop)\b"
        cleaned = query
        if ":" in query:
            prefix, after = query.split(":", 1)
            p_matches = len(re.findall(brand_or_model, prefix, re.IGNORECASE))
            a_matches = len(re.findall(brand_or_model, after, re.IGNORECASE))
            if a_matches > p_matches:
                cleaned = after
            elif p_matches > a_matches:
                cleaned = prefix
            else:
                cleaned = (
                    after if re.search(r"\b(?:vs\.?|versus|or)\b", after, re.IGNORECASE) else prefix
                )

        cleaned = re.sub(
            r"^(compare|difference between|what (?:are the )?differences between|which (?:is|has) (?:better|cheaper|lighter|longer)|is the|is|do|does|summary of differences between)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\s+(?:on|for|regarding|in terms of|based on)\s+(?:price|battery|weight|specs|display|screen|performance|ram|storage|features|ratings?).*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:(?:screen size|refresh rate|price|battery life|display technology|hdr format|audio and smart features|bluetooth version and driver size|price and processor breakdown|summary of differences) (?:and [a-z ]+ )?(?:of|between|for))\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"[\?:\.!]+", " ", cleaned)
        # Split on separators like 'and', 'vs', 'versus', 'or', 'with', 'compared to', 'against', 'than', commas
        parts = re.split(
            r"\b(?:and|vs\.?|versus|or|with|compared to|against|than|over|more than|worth [^\b]+ over)\b|,",
            cleaned,
            flags=re.IGNORECASE,
        )
        keywords = [p.strip() for p in parts if len(p.strip()) >= 2]
        if not keywords:
            # Fallback to non-stopword tokens
            tokens = [t.strip() for t in query.split() if len(t.strip()) >= 3]
            keywords = tokens if tokens else [query.strip()]
        return keywords

    def build_comparison_matrix(self, products: list[ProductSpec]) -> list[MatrixRow]:
        """Align product specifications side-by-side and determine winners."""
        if not products:
            return []

        rows: list[MatrixRow] = []

        # 1. Price comparison (lower is better)
        price_values = {p.sku: f"${p.price:,.2f}" for p in products}
        min_price = min(p.price for p in products)
        price_winners = [p.sku for p in products if p.price == min_price]
        rows.append(
            MatrixRow(
                feature="Price",
                values=price_values,
                winner_sku=price_winners[0] if len(price_winners) == 1 else None,
            )
        )

        # 2. Rating comparison (higher is better)
        rating_values = {
            p.sku: f"{p.rating:.1f} ★ ({p.review_count or 0})" if p.rating else "N/A"
            for p in products
        }
        valid_ratings = [(p.sku, p.rating) for p in products if p.rating is not None]
        rating_winner = None
        if valid_ratings:
            best_rating = max(r[1] for r in valid_ratings)
            top_raters = [r[0] for r in valid_ratings if r[1] == best_rating]
            if len(top_raters) == 1:
                rating_winner = top_raters[0]
        rows.append(
            MatrixRow(
                feature="Customer Rating",
                values=rating_values,
                winner_sku=rating_winner,
            )
        )

        # 3. Dynamic technical specifications alignment
        all_spec_keys: list[str] = []
        for p in products:
            for k in p.specifications.keys():
                if k not in all_spec_keys:
                    all_spec_keys.append(k)

        feature_labels = {
            "processor": "Processor / CPU",
            "ram_gb": "Memory (RAM)",
            "storage_gb": "Storage (SSD)",
            "battery_life_hours": "Battery Life",
            "display_size_in": "Display Size",
            "display_resolution": "Display Resolution",
            "weight_lbs": "Weight",
            "ports": "Ports & Connectivity",
        }

        for spec_key in all_spec_keys:
            label = feature_labels.get(spec_key, spec_key.replace("_", " ").title())
            val_map: dict[str, Any] = {}
            numeric_vals: list[tuple[str, float]] = []

            for p in products:
                raw_val = p.specifications.get(spec_key)
                if raw_val is None:
                    val_map[p.sku] = "Not specified"
                elif spec_key == "ram_gb":
                    val_map[p.sku] = f"{raw_val} GB"
                    if isinstance(raw_val, (int, float)):
                        numeric_vals.append((p.sku, float(raw_val)))
                elif spec_key == "storage_gb":
                    val_map[p.sku] = f"{raw_val} GB" if raw_val < 1000 else f"{raw_val / 1000:g} TB"
                    if isinstance(raw_val, (int, float)):
                        numeric_vals.append((p.sku, float(raw_val)))
                elif spec_key == "battery_life_hours":
                    val_map[p.sku] = f"Up to {raw_val} hours"
                    if isinstance(raw_val, (int, float)):
                        numeric_vals.append((p.sku, float(raw_val)))
                elif spec_key == "display_size_in":
                    val_map[p.sku] = f'{raw_val}"'
                elif spec_key == "weight_lbs":
                    val_map[p.sku] = f"{raw_val} lbs"
                    if isinstance(raw_val, (int, float)):
                        # For weight, lower is better
                        numeric_vals.append((p.sku, -float(raw_val)))
                elif isinstance(raw_val, list):
                    val_map[p.sku] = ", ".join(str(item) for item in raw_val)
                else:
                    val_map[p.sku] = str(raw_val)

            winner_sku = None
            if len(numeric_vals) == len(products):
                best_val = max(nv[1] for nv in numeric_vals)
                best_skus = [nv[0] for nv in numeric_vals if nv[1] == best_val]
                if len(best_skus) == 1:
                    winner_sku = best_skus[0]

            rows.append(MatrixRow(feature=label, values=val_map, winner_sku=winner_sku))

        return rows

    def synthesize_summary(self, products: list[ProductSpec], matrix: list[MatrixRow]) -> str:
        """Create grounded synthesis narrative strictly citing SKUs."""
        if not products:
            return "No matching products found in the catalog to compare."

        if len(products) == 1:
            p = products[0]
            return (
                f"Found single catalog item: {p.name} [SKU: {p.sku}] priced at ${p.price:,.2f}. "
                "Provide a second product to enable side-by-side comparison."
            )

        p1, p2 = products[0], products[1]
        summary_lines = [
            f"Direct comparison between {p1.name} [SKU: {p1.sku}] and {p2.name} [SKU: {p2.sku}]:",
        ]

        # Price narrative
        if p1.price < p2.price:
            diff = p2.price - p1.price
            summary_lines.append(
                f"- Price: {p1.name} [SKU: {p1.sku}] is ${diff:,.2f} more affordable at ${p1.price:,.2f} versus ${p2.price:,.2f} for {p2.name} [SKU: {p2.sku}]."
            )
        elif p2.price < p1.price:
            diff = p1.price - p2.price
            summary_lines.append(
                f"- Price: {p2.name} [SKU: {p2.sku}] is ${diff:,.2f} more affordable at ${p2.price:,.2f} versus ${p1.price:,.2f} for {p1.name} [SKU: {p1.sku}]."
            )
        else:
            summary_lines.append(
                f"- Price: Both products are priced identically at ${p1.price:,.2f}."
            )

        # Battery narrative
        b1 = p1.specifications.get("battery_life_hours")
        b2 = p2.specifications.get("battery_life_hours")
        if b1 is not None and b2 is not None:
            if b1 > b2:
                summary_lines.append(
                    f"- Battery Life: {p1.name} [SKU: {p1.sku}] leads with up to {b1} hours of battery life versus {b2} hours on {p2.name} [SKU: {p2.sku}]."
                )
            elif b2 > b1:
                summary_lines.append(
                    f"- Battery Life: {p2.name} [SKU: {p2.sku}] leads with up to {b2} hours of battery life versus {b1} hours on {p1.name} [SKU: {p1.sku}]."
                )

        # RAM / Processor narrative
        ram1 = p1.specifications.get("ram_gb")
        ram2 = p2.specifications.get("ram_gb")
        cpu1 = p1.specifications.get("processor")
        cpu2 = p2.specifications.get("processor")
        if ram1 or ram2 or cpu1 or cpu2:
            spec_desc = (
                f"- Performance: {p1.name} [SKU: {p1.sku}] features {cpu1 or 'N/A'} with {ram1 or 'N/A'}GB RAM; "
                f"{p2.name} [SKU: {p2.sku}] features {cpu2 or 'N/A'} with {ram2 or 'N/A'}GB RAM."
            )
            summary_lines.append(spec_desc)

        return "\n".join(summary_lines)

    def generate_recommendations(self, products: list[ProductSpec]) -> str | None:
        """Formulate tailored recommendations based on verified catalog specs."""
        if len(products) < 2:
            return None

        p1, p2 = products[0], products[1]
        rec_parts = ["Key Buying Recommendations:"]

        b1 = p1.specifications.get("battery_life_hours") or 0.0
        b2 = p2.specifications.get("battery_life_hours") or 0.0
        if b1 > b2:
            rec_parts.append(
                f"- Best for Battery & Portability: Choose {p1.name} [SKU: {p1.sku}] for all-day unplugged productivity."
            )
        elif b2 > b1:
            rec_parts.append(
                f"- Best for Battery & Portability: Choose {p2.name} [SKU: {p2.sku}] for extended endurance on the go."
            )

        if p1.price < p2.price:
            rec_parts.append(
                f"- Best Value for Money: {p1.name} [SKU: {p1.sku}] offers excellent performance per dollar."
            )
        elif p2.price < p1.price:
            rec_parts.append(
                f"- Best Value for Money: {p2.name} [SKU: {p2.sku}] provides maximum cost efficiency."
            )

        return "\n".join(rec_parts) if len(rec_parts) > 1 else None

    def rank_and_select_products(
        self, products: list[ProductSpec], keywords: list[str]
    ) -> list[ProductSpec]:
        """Rank products to ensure top 2 best match candidate comparison keywords."""
        if len(products) <= 2 or len(keywords) < 2:
            return products

        stopwords = {
            "vs",
            "and",
            "or",
            "compare",
            "between",
            "the",
            "with",
            "inch",
            "laptop",
            "tablet",
            "headphones",
            "smart",
            "home",
            "tv",
        }
        selected: list[ProductSpec] = []
        used_skus: set[str] = set()

        for kw in keywords[:2]:
            kw_tokens = set(re.findall(r"[a-z0-9]+", kw.lower())) - stopwords
            best_p: ProductSpec | None = None
            best_score = -1
            for p in products:
                if p.sku in used_skus:
                    continue
                p_tokens = set(re.findall(r"[a-z0-9]+", f"{p.name} {p.brand}".lower()))
                score = len(kw_tokens & p_tokens)
                if score > best_score:
                    best_score = score
                    best_p = p
            if best_p and best_score > 0:
                selected.append(best_p)
                used_skus.add(best_p.sku)

        # Fill remaining products from original list
        for p in products:
            if p.sku not in used_skus:
                selected.append(p)
                used_skus.add(p.sku)

        return selected

    def compare(
        self,
        query: str,
        category: str | None = None,
        session_id: str | None = None,
    ) -> CompareResponse:
        """Execute full end-to-end grounded comparison pipeline with OpenTelemetry tracing."""
        tracer = get_tracer("app.agent")

        with tracer.start_as_current_span("catalog_comparison.orchestrate") as span:
            span.set_attribute("query", query)
            span.set_attribute("category", category or "")
            if session_id:
                span.set_attribute("session_id", session_id)

            with tracer.start_as_current_span("extract_keywords"):
                keywords = self.extract_keywords(query)
                span.set_attribute("keywords", str(keywords))
                logger.info("Parsed keywords %s from query: %s", keywords, query)

            try:
                catalog_rows = query_catalog(
                    keywords=keywords,
                    category=category,
                    client=self.bq_client,
                )
            except Exception as err:
                logger.warning("BigQuery catalog query encountered an error: %s", err)
                catalog_rows = []

            trace_id = get_current_trace_id()

            if not catalog_rows:
                span.set_attribute("product_count", 0)
                span.set_attribute("target_skus", "")
                return CompareResponse(
                    summary=f"No matching products found in the catalog for query: '{query}'. Please check your search terms.",
                    products=[],
                    comparison_matrix=[],
                    citations=[],
                    recommendations="Try searching for broader keywords like 'MacBook', 'Dell', or specify a valid category.",
                    session_id=session_id,
                    trace_id=trace_id,
                )

            # Convert to ProductSpec schemas and rank products to match query intent
            products = [ProductSpec(**row) for row in catalog_rows]
            products = self.rank_and_select_products(products, keywords)
            target_skus = [p.sku for p in products]
            span.set_attribute("product_count", len(products))
            span.set_attribute("target_skus", ",".join(target_skus))

            # Extract strict citations
            citations = [
                Citation(sku=p.sku, url=p.url or f"https://www.bestbuy.com/site/sku/{p.sku}.p")
                for p in products
            ]

            # Build comparison matrix
            with tracer.start_as_current_span("build_comparison_matrix"):
                matrix = self.build_comparison_matrix(products)

            # Synthesize narrative with SKU citations
            with tracer.start_as_current_span("synthesize_summary"):
                summary = self.synthesize_summary(products, matrix)
                recommendations = self.generate_recommendations(products)

            return CompareResponse(
                summary=summary,
                products=products,
                comparison_matrix=matrix,
                citations=citations,
                recommendations=recommendations,
                session_id=session_id,
                trace_id=trace_id,
            )
