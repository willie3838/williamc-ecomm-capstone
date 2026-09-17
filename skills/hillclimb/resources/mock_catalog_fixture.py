"""Mock BigQuery catalog dataset for unit tests and local simulations."""

from unittest.mock import MagicMock

MOCK_PRODUCTS = [
    {
        "sku": "6534606",
        "name": "Apple MacBook Air 13.6\" Laptop - M3 chip - 16GB Memory - 512GB SSD",
        "brand": "Apple",
        "category": "Laptops",
        "price": 1099.0,
        "rating": 4.8,
        "review_count": 1250,
        "specifications": {
            "processor": "Apple M3 8-core",
            "ram_gb": 16,
            "storage_gb": 512,
            "battery_life_hours": 18.0,
            "weight_lbs": 2.7,
        },
        "url": "https://www.bestbuy.com/site/sku/6534606.p",
        "in_stock": True,
    },
    {
        "sku": "6575132",
        "name": "Dell XPS 13\" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD",
        "brand": "Dell",
        "category": "Laptops",
        "price": 1199.0,
        "rating": 4.5,
        "review_count": 430,
        "specifications": {
            "processor": "Intel Core Ultra 7 155H",
            "ram_gb": 16,
            "storage_gb": 512,
            "battery_life_hours": 14.0,
            "weight_lbs": 2.6,
        },
        "url": "https://www.bestbuy.com/site/sku/6575132.p",
        "in_stock": True,
    },
    {
        "sku": "6505727",
        "name": "Sony WH-1000XM5 Wireless Noise-Canceling Headphones",
        "brand": "Sony",
        "category": "Headphones",
        "price": 399.99,
        "rating": 4.7,
        "review_count": 3100,
        "specifications": {
            "battery_life_hours": 30.0,
            "noise_cancellation": "Active Noise Canceling with Auto NC Optimizer",
            "weight_oz": 8.8,
        },
        "url": "https://www.bestbuy.com/site/sku/6505727.p",
        "in_stock": True,
    },
]


def create_mock_bigquery_client(products: list[dict] = MOCK_PRODUCTS) -> MagicMock:
    """Returns a MagicMock simulating google.cloud.bigquery.Client."""
    mock_client = MagicMock()
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = iter(products)
    mock_client.query.return_value = mock_query_job
    return mock_client
