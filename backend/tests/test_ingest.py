"""Unit tests for BigQuery catalog ingestion and schema definition."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.cloud.exceptions import Conflict, GoogleCloudError
from pydantic import ValidationError

from app.data.ingest import BigQueryCatalogIngestor, IngestionResult
from app.models.product import ProductRecord


@pytest.fixture
def sample_product_dict() -> dict:
    return {
        "sku": "6534606",
        "name": 'Apple MacBook Air 13.6" Laptop - M3 chip - 16GB Memory - 512GB SSD',
        "brand": "Apple",
        "category": "Laptops",
        "price": 1099.0,
        "shortDescription": "Thin, fast MacBook Air with Apple M3 chip.",
        "longDescription": "The Apple MacBook Air 13.6-inch with M3 chip offers incredible battery life and performance.",
        "rating": 4.8,
        "review_count": 1250,
        "specifications": {
            "processor": "Apple M3 8-core",
            "ram_gb": 16,
            "storage_gb": 512,
            "battery_life_hours": 18.0,
            "weight_lbs": 2.7,
        },
        "url": "https://www.techbuy.com/site/sku/6534606.p",
        "image_url": "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6534/6534606_sd.jpg",
        "in_stock": True,
    }


def test_product_record_valid(sample_product_dict: dict) -> None:
    """Verify that a valid product dictionary instantiates ProductRecord cleanly."""
    record = ProductRecord(**sample_product_dict)
    assert record.sku == "6534606"
    assert record.price == 1099.0
    assert record.specifications["processor"] == "Apple M3 8-core"
    assert record.in_stock is True
    assert record.created_at is not None
    assert record.updated_at is not None

    bq_row = record.to_bigquery_row()
    assert bq_row["sku"] == "6534606"
    assert bq_row["specifications"]["ram_gb"] == 16
    assert isinstance(bq_row["updated_at"], str)


def test_product_record_invalid_price(sample_product_dict: dict) -> None:
    """Verify that negative price raises ValidationError."""
    sample_product_dict["price"] = -10.0
    with pytest.raises(ValidationError):
        ProductRecord(**sample_product_dict)


def test_product_record_invalid_rating(sample_product_dict: dict) -> None:
    """Verify that rating outside [0.0, 5.0] raises ValidationError."""
    sample_product_dict["rating"] = 5.5
    with pytest.raises(ValidationError):
        ProductRecord(**sample_product_dict)


def test_product_record_missing_required(sample_product_dict: dict) -> None:
    """Verify that omitting required field raises ValidationError."""
    del sample_product_dict["name"]
    with pytest.raises(ValidationError):
        ProductRecord(**sample_product_dict)


def test_product_record_csv_parsing() -> None:
    """Verify parsing a flat string dictionary from CSV into ProductRecord."""
    csv_row = {
        "sku": "6575132",
        "name": 'Dell XPS 13" - Intel Core Ultra 7',
        "brand": "Dell",
        "category": "Laptops",
        "price": "1199.0",
        "shortDescription": "Sleek Dell XPS 13.",
        "longDescription": "High performance ultrabook.",
        "rating": "4.5",
        "review_count": "430",
        "specifications": '{"processor": "Intel Core Ultra 7 155H", "ram_gb": 16, "storage_gb": 512}',
        "url": "https://www.techbuy.com/site/sku/6575132.p",
        "image_url": "",
        "in_stock": "True",
    }
    record = ProductRecord.model_validate_csv_row(csv_row)
    assert record.sku == "6575132"
    assert record.price == 1199.0
    assert record.rating == 4.5
    assert record.review_count == 430
    assert record.in_stock is True
    assert record.specifications["processor"] == "Intel Core Ultra 7 155H"
    assert record.image_url is None


def test_product_record_csv_invalid_specs() -> None:
    """Verify that malformed JSON in specifications CSV column raises ValueError."""
    csv_row = {
        "sku": "1234567",
        "name": "Test Item",
        "brand": "Test Brand",
        "category": "Laptops",
        "price": "99.99",
        "shortDescription": "Test item short description.",
        "specifications": "{not valid json}",
        "in_stock": "true",
    }
    with pytest.raises(ValueError, match="Invalid JSON"):
        ProductRecord.model_validate_csv_row(csv_row)


def test_schema_definition() -> None:
    """Verify that BigQuery schema defines required fields, partitioning, and clustering."""
    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    schema = ingestor.get_schema()

    schema_dict = {field.name: field for field in schema}
    assert "sku" in schema_dict
    assert schema_dict["sku"].field_type == "STRING"
    assert schema_dict["sku"].mode == "REQUIRED"

    assert "name" in schema_dict
    assert "brand" in schema_dict
    assert "category" in schema_dict
    assert schema_dict["price"].field_type in ("FLOAT", "FLOAT64")
    assert schema_dict["shortDescription"].mode == "REQUIRED"
    assert schema_dict["longDescription"].mode == "NULLABLE"
    assert schema_dict["specifications"].field_type == "JSON"
    assert schema_dict["specifications"].mode == "REQUIRED"
    assert schema_dict["in_stock"].field_type in ("BOOLEAN", "BOOL")
    assert schema_dict["updated_at"].field_type == "TIMESTAMP"
    assert schema_dict["updated_at"].mode == "REQUIRED"


def test_load_from_json(tmp_path: Path, sample_product_dict: dict) -> None:
    """Verify loading and validating product records from a JSON file."""
    json_file = tmp_path / "test_products.json"
    json_file.write_text(json.dumps([sample_product_dict]), encoding="utf-8")

    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    products = ingestor.load_from_json(json_file)

    assert len(products) == 1
    assert products[0].sku == "6534606"
    assert products[0].specifications["ram_gb"] == 16


def test_load_from_csv(tmp_path: Path) -> None:
    """Verify loading and validating product records from a CSV file."""
    csv_file = tmp_path / "test_products.csv"
    csv_content = (
        "sku,name,brand,category,price,shortDescription,longDescription,rating,review_count,specifications,url,image_url,in_stock\n"
        '6505727,"Sony WH-1000XM5 Headphones",Sony,Headphones,399.99,"Active noise canceling.",,4.7,3100,"{""battery_life_hours"": 30.0}",https://test.com,,true\n'
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    products = ingestor.load_from_csv(csv_file)

    assert len(products) == 1
    assert products[0].sku == "6505727"
    assert products[0].brand == "Sony"
    assert products[0].specifications["battery_life_hours"] == 30.0
    assert products[0].in_stock is True


def test_create_dataset_if_not_exists_already_exists() -> None:
    """Verify handling when dataset already exists."""
    mock_client = MagicMock()
    mock_client.create_dataset.side_effect = Conflict("Dataset already exists")

    ingestor = BigQueryCatalogIngestor(project_id="test-project", client=mock_client)
    dataset = ingestor.create_dataset_if_not_exists()
    assert dataset is not None
    mock_client.create_dataset.assert_called_once()


def test_create_dataset_if_not_exists_new() -> None:
    """Verify creating a new dataset when it does not exist."""
    mock_client = MagicMock()
    mock_dataset = MagicMock()
    mock_client.create_dataset.return_value = mock_dataset

    ingestor = BigQueryCatalogIngestor(project_id="test-project", client=mock_client)
    dataset = ingestor.create_dataset_if_not_exists(location="us-central1")
    assert dataset == mock_dataset
    mock_client.create_dataset.assert_called_once()


def test_create_table_if_not_exists_already_exists() -> None:
    """Verify handling when table already exists."""
    mock_client = MagicMock()
    mock_client.create_table.side_effect = Conflict("Table already exists")

    ingestor = BigQueryCatalogIngestor(project_id="test-project", client=mock_client)
    table = ingestor.create_table_if_not_exists()
    assert table is not None
    mock_client.create_table.assert_called_once()


def test_create_table_if_not_exists_new() -> None:
    """Verify creating a new table with partitioning and clustering."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.create_table.return_value = mock_table

    ingestor = BigQueryCatalogIngestor(project_id="test-project", client=mock_client)
    table = ingestor.create_table_if_not_exists()
    assert table == mock_table

    created_table_arg = mock_client.create_table.call_args[0][0]
    assert created_table_arg.time_partitioning.field == "updated_at"
    assert created_table_arg.clustering_fields == ["category", "brand", "sku"]


def test_ingest_products_dry_run(sample_product_dict: dict) -> None:
    """Verify that dry_run=True performs validation without calling BigQuery."""
    mock_client = MagicMock()
    ingestor = BigQueryCatalogIngestor(project_id="test-project", client=mock_client)
    products = [ProductRecord(**sample_product_dict)]

    result = ingestor.ingest_products(products, dry_run=True)
    assert isinstance(result, IngestionResult)
    assert result.total_records == 1
    assert result.inserted_records == 1
    assert result.failed_records == 0
    assert result.dry_run is True
    assert result.errors == []
    mock_client.create_dataset.assert_not_called()
    mock_client.create_table.assert_not_called()
    mock_client.load_table_from_json.assert_not_called()


def test_ingest_products_success(sample_product_dict: dict) -> None:
    """Verify successful ingestion into BigQuery."""
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = None
    mock_job.errors = None
    mock_client.load_table_from_json.return_value = mock_job

    ingestor = BigQueryCatalogIngestor(project_id="test-project", client=mock_client)
    products = [ProductRecord(**sample_product_dict)]

    result = ingestor.ingest_products(products, dry_run=False, create_table=True)
    assert result.total_records == 1
    assert result.inserted_records == 1
    assert result.failed_records == 0
    assert result.dry_run is False
    assert result.errors == []
    mock_client.load_table_from_json.assert_called_once()


def test_ingest_products_empty() -> None:
    """Verify ingesting empty product list returns zero counts without error."""
    mock_client = MagicMock()
    ingestor = BigQueryCatalogIngestor(project_id="test-project", client=mock_client)
    result = ingestor.ingest_products([], dry_run=False)
    assert result.total_records == 0
    assert result.inserted_records == 0
    assert result.failed_records == 0
    mock_client.load_table_from_json.assert_not_called()


def test_ingest_products_bigquery_error(sample_product_dict: dict) -> None:
    """Verify graceful handling when BigQuery load job fails."""
    mock_client = MagicMock()
    mock_client.load_table_from_json.side_effect = GoogleCloudError("BigQuery quota exceeded")

    ingestor = BigQueryCatalogIngestor(project_id="test-project", client=mock_client)
    products = [ProductRecord(**sample_product_dict)]

    result = ingestor.ingest_products(products, dry_run=False, create_table=False)
    assert result.total_records == 1
    assert result.inserted_records == 0
    assert result.failed_records == 1
    assert len(result.errors) > 0
    assert "quota exceeded" in result.errors[0]


def test_catalog_seed_json_validity() -> None:
    """Verify that backend/src/app/data/catalog_seed.json exists, parses, and covers benchmark products."""
    seed_file = Path(__file__).parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    assert seed_file.exists(), f"Seed catalog file not found at {seed_file}"

    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    products = ingestor.load_from_json(seed_file)
    assert len(products) >= 6, "Seed dataset should have at least 6 products"

    sku_map = {p.sku: p for p in products}

    # Verify benchmark expected SKUs from benchmark_queries.json
    benchmark_skus = ["6534606", "6575132", "6579601", "6546522", "6505727", "6553823"]
    for sku in benchmark_skus:
        assert sku in sku_map, f"Benchmark SKU {sku} missing in seed catalog"
        prod = sku_map[sku]
        assert prod.price > 0
        assert prod.specifications
        assert prod.in_stock is True

    # Verify category coverage
    categories = {p.category for p in products}
    assert "Laptops" in categories
    assert "Tablets" in categories
    assert "Headphones" in categories


def test_cli_dry_run(tmp_path: Path, sample_product_dict: dict) -> None:
    """Verify CLI dry run execution."""
    json_file = tmp_path / "products.json"
    json_file.write_text(json.dumps([sample_product_dict]), encoding="utf-8")

    from app.data.ingest import main

    with patch("sys.argv", ["ingest.py", "--file", str(json_file), "--dry-run"]):
        exit_code = main()
        assert exit_code == 0


def test_client_lazy_initialization() -> None:
    """Verify lazy BigQuery client initialization with project ID."""
    with patch("google.cloud.bigquery.Client") as mock_bq_cls:
        ingestor = BigQueryCatalogIngestor(project_id="test-proj")
        client = ingestor.client
        assert client is not None
        mock_bq_cls.assert_called_once_with(project="test-proj")


def test_load_from_json_file_not_found(tmp_path: Path) -> None:
    """Verify FileNotFoundError when json file does not exist."""
    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    with pytest.raises(FileNotFoundError):
        ingestor.load_from_json(tmp_path / "non_existent.json")


def test_load_from_json_invalid_record(tmp_path: Path) -> None:
    """Verify ValueError when record in json fails validation."""
    json_file = tmp_path / "bad.json"
    json_file.write_text(json.dumps([{"sku": "bad", "name": "x"}]), encoding="utf-8")
    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    with pytest.raises(ValueError, match="Validation failed"):
        ingestor.load_from_json(json_file)


def test_load_from_csv_file_not_found(tmp_path: Path) -> None:
    """Verify FileNotFoundError when csv file does not exist."""
    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    with pytest.raises(FileNotFoundError):
        ingestor.load_from_csv(tmp_path / "non_existent.csv")


def test_load_from_csv_invalid_record(tmp_path: Path) -> None:
    """Verify ValueError when record in csv fails validation."""
    csv_file = tmp_path / "bad.csv"
    csv_file.write_text("sku,name,price\n123,x,not-a-float\n", encoding="utf-8")
    ingestor = BigQueryCatalogIngestor(project_id="test-project")
    with pytest.raises(ValueError, match="Validation failed"):
        ingestor.load_from_csv(csv_file)


def test_ingest_products_with_job_errors(sample_product_dict: dict) -> None:
    """Verify handling when BigQuery job returns errors list."""
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = None
    mock_job.errors = [{"message": "Invalid JSON format in row 0"}]
    mock_client.load_table_from_json.return_value = mock_job

    ingestor = BigQueryCatalogIngestor(project_id="test-project", client=mock_client)
    products = [ProductRecord(**sample_product_dict)]

    result = ingestor.ingest_products(products, dry_run=False, create_table=False)
    assert result.total_records == 1
    assert result.inserted_records == 0
    assert result.failed_records == 1
    assert len(result.errors) == 1
    assert "Invalid JSON" in result.errors[0]


def test_cli_csv_format(tmp_path: Path) -> None:
    """Verify CLI execution with CSV format."""
    csv_file = tmp_path / "products.csv"
    csv_content = (
        "sku,name,brand,category,price,shortDescription,longDescription,rating,review_count,specifications,url,image_url,in_stock\n"
        '6505727,"Sony Headphones",Sony,Headphones,399.99,"Active noise canceling.",,4.7,3100,"{""battery_life_hours"": 30.0}",https://test.com,,true\n'
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    from app.data.ingest import main

    with patch("sys.argv", ["ingest.py", "--file", str(csv_file), "--format", "csv", "--dry-run"]):
        exit_code = main()
        assert exit_code == 0


def test_cli_failure_exit_code(tmp_path: Path, sample_product_dict: dict) -> None:
    """Verify CLI returns exit code 1 when ingestion encounters errors."""
    json_file = tmp_path / "products.json"
    json_file.write_text(json.dumps([sample_product_dict]), encoding="utf-8")

    mock_client = MagicMock()
    mock_client.load_table_from_json.side_effect = GoogleCloudError("Connection error")

    from app.data.ingest import main

    with patch("google.cloud.bigquery.Client", return_value=mock_client):
        with patch("sys.argv", ["ingest.py", "--file", str(json_file), "--no-create-table"]):
            exit_code = main()
            assert exit_code == 1


def test_cli_exception_handling(tmp_path: Path) -> None:
    """Verify CLI returns exit code 1 when an unhandled exception occurs."""
    from app.data.ingest import main

    with patch("sys.argv", ["ingest.py", "--file", str(tmp_path / "missing.json")]):
        exit_code = main()
        assert exit_code == 1


def test_product_specifications_not_dict(sample_product_dict: dict) -> None:
    """Verify that specifications field fails if not a dict."""
    sample_product_dict["specifications"] = "not a dict"
    with pytest.raises(ValidationError):
        ProductRecord(**sample_product_dict)
