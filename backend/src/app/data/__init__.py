"""Data management and ingestion module."""

from app.data.ingest import BigQueryCatalogIngestor, IngestionResult

__all__ = ["BigQueryCatalogIngestor", "IngestionResult"]
