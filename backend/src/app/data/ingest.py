"""BigQuery Catalog Ingestion and Schema Management Service."""

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from google.cloud import bigquery
from google.cloud.exceptions import Conflict, GoogleCloudError
from pydantic import BaseModel, Field

from app.models.product import ProductRecord

logger = logging.getLogger("catalog.ingest")

DEFAULT_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "fde-bestbuy-sandbox-dev-508321")
DEFAULT_DATASET_ID = "catalog"
DEFAULT_TABLE_ID = "products"
DEFAULT_LOCATION = "us-central1"


class IngestionResult(BaseModel):
    """Result summary of a catalog ingestion operation."""

    total_records: int = Field(..., description="Total records evaluated for ingestion")
    inserted_records: int = Field(..., description="Count of successfully ingested records")
    failed_records: int = Field(0, description="Count of records that failed ingestion")
    dry_run: bool = Field(False, description="Whether operation was executed in dry-run mode")
    errors: list[str] = Field(
        default_factory=list, description="List of error messages encountered"
    )


class BigQueryCatalogIngestor:
    """Manages schema creation and data ingestion into Google Cloud BigQuery."""

    def __init__(
        self,
        project_id: str = DEFAULT_PROJECT_ID,
        dataset_id: str = DEFAULT_DATASET_ID,
        table_id: str = DEFAULT_TABLE_ID,
        client: bigquery.Client | None = None,
    ) -> None:
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.table_id = table_id
        self._client = client

    @property
    def client(self) -> bigquery.Client:
        """Lazily initialize BigQuery client if not provided."""
        if self._client is None:
            self._client = bigquery.Client(project=self.project_id)
        return self._client

    @property
    def table_ref(self) -> str:
        """Full BigQuery table identifier."""
        return f"{self.project_id}.{self.dataset_id}.{self.table_id}"

    def get_schema(self) -> list[bigquery.SchemaField]:
        """Define explicit BigQuery schema with semi-structured JSON specifications."""
        return [
            bigquery.SchemaField(
                name="sku",
                field_type="STRING",
                mode="REQUIRED",
                description="Unique Best Buy SKU identifier (Primary Key, e.g. '6534606')",
            ),
            bigquery.SchemaField(
                name="name",
                field_type="STRING",
                mode="REQUIRED",
                description="Full commercial product title",
            ),
            bigquery.SchemaField(
                name="brand",
                field_type="STRING",
                mode="REQUIRED",
                description="Manufacturer brand name (e.g. 'Apple', 'Dell', 'Sony')",
            ),
            bigquery.SchemaField(
                name="category",
                field_type="STRING",
                mode="REQUIRED",
                description="Product taxonomy category (e.g. 'Laptops', 'Tablets', 'Headphones')",
            ),
            bigquery.SchemaField(
                name="price",
                field_type="FLOAT64",
                mode="REQUIRED",
                description="Current retail price in USD",
            ),
            bigquery.SchemaField(
                name="shortDescription",
                field_type="STRING",
                mode="REQUIRED",
                description="Brief marketing overview and key features",
            ),
            bigquery.SchemaField(
                name="longDescription",
                field_type="STRING",
                mode="NULLABLE",
                description="Complete detailed product summary",
            ),
            bigquery.SchemaField(
                name="rating",
                field_type="FLOAT64",
                mode="NULLABLE",
                description="Average customer review rating (1.0 to 5.0)",
            ),
            bigquery.SchemaField(
                name="review_count",
                field_type="INT64",
                mode="NULLABLE",
                description="Total count of customer reviews",
            ),
            bigquery.SchemaField(
                name="specifications",
                field_type="JSON",
                mode="REQUIRED",
                description="Semi-structured key-value technical specifications",
            ),
            bigquery.SchemaField(
                name="url",
                field_type="STRING",
                mode="NULLABLE",
                description="Direct URL link to Best Buy product listing",
            ),
            bigquery.SchemaField(
                name="image_url",
                field_type="STRING",
                mode="NULLABLE",
                description="CDN URL for high-resolution product photography",
            ),
            bigquery.SchemaField(
                name="in_stock",
                field_type="BOOL",
                mode="REQUIRED",
                description="Current retail inventory availability",
            ),
            bigquery.SchemaField(
                name="created_at",
                field_type="TIMESTAMP",
                mode="NULLABLE",
                description="Record creation timestamp",
            ),
            bigquery.SchemaField(
                name="updated_at",
                field_type="TIMESTAMP",
                mode="REQUIRED",
                description="Record update timestamp (Partitioning Key)",
            ),
        ]

    def create_dataset_if_not_exists(self, location: str = DEFAULT_LOCATION) -> bigquery.Dataset:
        """Ensure BigQuery catalog dataset exists with proper regional location."""
        dataset_ref = bigquery.DatasetReference(self.project_id, self.dataset_id)
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = location
        dataset.description = "E-commerce product catalog for comparison agent"

        try:
            created = self.client.create_dataset(dataset, exists_ok=True)
            logger.info("Dataset '%s.%s' verified or created.", self.project_id, self.dataset_id)
            return created
        except Conflict:
            logger.info("Dataset '%s.%s' already exists.", self.project_id, self.dataset_id)
            return dataset

    def create_table_if_not_exists(self) -> bigquery.Table:
        """Ensure BigQuery catalog products table exists with partitioning and clustering."""
        table_ref = bigquery.TableReference(
            bigquery.DatasetReference(self.project_id, self.dataset_id),
            self.table_id,
        )
        table = bigquery.Table(table_ref, schema=self.get_schema())

        # Partition by day on updated_at
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="updated_at",
        )

        # Cluster by category, brand, sku for sub-second query performance
        table.clustering_fields = ["category", "brand", "sku"]
        table.description = "Best Buy catalog products partitioned by updated_at and clustered by category/brand/sku"

        try:
            created = self.client.create_table(table, exists_ok=True)
            logger.info("Table '%s' verified or created.", self.table_ref)
            return created
        except Conflict:
            logger.info("Table '%s' already exists.", self.table_ref)
            return table

    def load_from_json(self, file_path: Path | str) -> list[ProductRecord]:
        """Load and validate product records from a JSON file."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Catalog file not found: {path}")

        content = path.read_text(encoding="utf-8")
        raw_items: list[dict[str, Any]] = json.loads(content)

        records: list[ProductRecord] = []
        for index, item in enumerate(raw_items):
            try:
                record = ProductRecord(**item)
                records.append(record)
            except Exception as exc:
                raise ValueError(
                    f"Validation failed for item index {index} (SKU: {item.get('sku')}): {exc}"
                ) from exc

        return records

    def load_from_csv(self, file_path: Path | str) -> list[ProductRecord]:
        """Load and validate product records from a CSV file with stringified JSON specs."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Catalog file not found: {path}")

        records: list[ProductRecord] = []
        with path.open(mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader):
                try:
                    record = ProductRecord.model_validate_csv_row(row)
                    records.append(record)
                except Exception as exc:
                    raise ValueError(
                        f"Validation failed for CSV row {row_idx + 1} (SKU: {row.get('sku')}): {exc}"
                    ) from exc

        return records

    def ingest_products(
        self,
        products: list[ProductRecord],
        dry_run: bool = False,
        create_table: bool = True,
    ) -> IngestionResult:
        """Batch ingest validated ProductRecords into BigQuery.

        Args:
            products: List of validated ProductRecord objects.
            dry_run: If True, validate schemas without writing to BigQuery.
            create_table: If True, ensure dataset and table exist before loading.

        Returns:
            IngestionResult summary with counts and errors.
        """
        total = len(products)
        if total == 0:
            logger.warning("No product records provided for ingestion.")
            return IngestionResult(
                total_records=0, inserted_records=0, failed_records=0, dry_run=dry_run
            )

        # Validate all records can serialize to BigQuery schema
        rows = [p.to_bigquery_row() for p in products]

        if dry_run:
            logger.info(
                "DRY RUN: Validated %d catalog products successfully. Skipping BigQuery load.",
                total,
            )
            return IngestionResult(
                total_records=total,
                inserted_records=total,
                failed_records=0,
                dry_run=True,
                errors=[],
            )

        if create_table:
            self.create_dataset_if_not_exists()
            self.create_table_if_not_exists()

        logger.info("Submitting BigQuery load job for %d rows into %s...", total, self.table_ref)

        job_config = bigquery.LoadJobConfig(
            schema=self.get_schema(),
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        try:
            job = self.client.load_table_from_json(
                rows,
                self.table_ref,
                job_config=job_config,
            )
            job.result()  # Wait for the load job to complete

            if job.errors:
                error_msgs = [str(err) for err in job.errors]
                logger.error("BigQuery load job finished with errors: %s", error_msgs)
                return IngestionResult(
                    total_records=total,
                    inserted_records=0,
                    failed_records=total,
                    dry_run=False,
                    errors=error_msgs,
                )

            logger.info(
                "Successfully ingested %d products into BigQuery table %s.", total, self.table_ref
            )
            return IngestionResult(
                total_records=total,
                inserted_records=total,
                failed_records=0,
                dry_run=False,
                errors=[],
            )

        except GoogleCloudError as exc:
            logger.error("GoogleCloudError during BigQuery ingestion: %s", exc)
            return IngestionResult(
                total_records=total,
                inserted_records=0,
                failed_records=total,
                dry_run=False,
                errors=[str(exc)],
            )


def main() -> int:
    """CLI entrypoint for BigQuery catalog ingestion."""
    parser = argparse.ArgumentParser(description="Best Buy BigQuery Catalog Ingestion Tool")
    parser.add_argument(
        "--file",
        type=str,
        default=str(Path(__file__).parent / "catalog_seed.json"),
        help="Path to catalog data file (JSON or CSV)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "csv", "auto"],
        default="auto",
        help="Data format (json, csv, or auto-detect)",
    )
    parser.add_argument(
        "--project-id",
        type=str,
        default=DEFAULT_PROJECT_ID,
        help="GCP Project ID",
    )
    parser.add_argument(
        "--dataset-id",
        type=str,
        default=DEFAULT_DATASET_ID,
        help="BigQuery dataset ID",
    )
    parser.add_argument(
        "--table-id",
        type=str,
        default=DEFAULT_TABLE_ID,
        help="BigQuery table ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate records locally without inserting into BigQuery",
    )
    parser.add_argument(
        "--no-create-table",
        action="store_true",
        help="Skip dataset/table creation step",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    file_path = Path(args.file)
    fmt = args.format
    if fmt == "auto":
        fmt = "csv" if file_path.suffix.lower() == ".csv" else "json"

    ingestor = BigQueryCatalogIngestor(
        project_id=args.project_id,
        dataset_id=args.dataset_id,
        table_id=args.table_id,
    )

    try:
        if fmt == "csv":
            products = ingestor.load_from_csv(file_path)
        else:
            products = ingestor.load_from_json(file_path)

        result = ingestor.ingest_products(
            products=products,
            dry_run=args.dry_run,
            create_table=not args.no_create_table,
        )

        print("\n=== INGESTION SUMMARY ===")
        print(f"Total Records:    {result.total_records}")
        print(f"Inserted Records: {result.inserted_records}")
        print(f"Failed Records:   {result.failed_records}")
        print(f"Dry Run:          {result.dry_run}")
        if result.errors:
            print(f"Errors:           {result.errors}")

        return 0 if result.failed_records == 0 else 1

    except Exception as err:
        logger.exception("Catalog ingestion failed: %s", err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
