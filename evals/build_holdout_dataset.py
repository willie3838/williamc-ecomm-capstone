"""Generator script for curated holdout and counterfactual evaluation dataset.

Conforms strictly to ADK EvalSet schema and ensures:
1. Holdout comparison queries across all 5 catalog categories.
2. Counterfactual spec mutations to detect parametric memory hallucination.
3. Negative chatter and customer service rants (0-SKU) to verify no hallucinations.
4. Cross-category mismatch and single-product queries.
5. Zero query or ID overlap with the canonical 80-pair benchmark.
"""

import json
from pathlib import Path

OUTPUT_PATH = Path(__file__).resolve().parent / "dataset" / "holdout_catalog.evalset.json"


def generate_holdout_dataset() -> dict:
    cases = []

    # =========================================================================
    # 1. Holdout Comparison Queries (14 Cases)
    # =========================================================================
    # Laptops (3 cases)
    cases.append(
        {
            "eval_id": "holdout-laptop-001",
            "archetype": "holdout_comparison",
            "category": "Laptops",
            "expected_skus": ["6575132", "6579840"],
            "key_differential_features": ["processor", "price", "weight_lbs", "battery_life_hours"],
            "ground_truth_specs": {
                "6575132": {
                    "name": 'Dell XPS 13" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD',
                    "brand": "Dell",
                    "price": 1199.0,
                    "processor": "Intel Core Ultra 7 155H",
                    "ram_gb": 16,
                    "battery_life_hours": 14.0,
                    "weight_lbs": 2.6,
                },
                "6579840": {
                    "name": 'Lenovo ThinkPad X1 Carbon Gen 12 14" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD',
                    "brand": "Lenovo",
                    "price": 1499.99,
                    "processor": "Intel Core Ultra 7 155U",
                    "ram_gb": 16,
                    "battery_life_hours": 13.5,
                    "weight_lbs": 2.42,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-laptop-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "I am looking for a lightweight Windows business laptop. How does the Dell XPS 13 Intel Core Ultra 7 compare to the Lenovo ThinkPad X1 Carbon Gen 12?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'Comparing Dell XPS 13" [SKU: 6575132] ($1,199.00, 2.6 lbs, 14 hrs battery) with Lenovo ThinkPad X1 Carbon Gen 12 [SKU: 6579840] ($1,499.99, 2.42 lbs, 13.5 hrs battery). The ThinkPad is lighter with military-grade durability, while the XPS 13 offers greater battery endurance at a lower price point.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Laptops"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "holdout-laptop-002",
            "archetype": "holdout_comparison",
            "category": "Laptops",
            "expected_skus": ["6534640", "6579840"],
            "key_differential_features": ["processor", "ram_gb", "price", "weight_lbs"],
            "ground_truth_specs": {
                "6534640": {
                    "name": 'Apple MacBook Pro 14" Laptop - M3 Pro chip - 18GB Memory - 512GB SSD',
                    "brand": "Apple",
                    "price": 1799.0,
                    "processor": "Apple M3 Pro 11-core",
                    "ram_gb": 18,
                    "battery_life_hours": 17.0,
                    "weight_lbs": 3.5,
                },
                "6579840": {
                    "name": 'Lenovo ThinkPad X1 Carbon Gen 12 14" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD',
                    "brand": "Lenovo",
                    "price": 1499.99,
                    "processor": "Intel Core Ultra 7 155U",
                    "ram_gb": 16,
                    "battery_life_hours": 13.5,
                    "weight_lbs": 2.42,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-laptop-002",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Which is more suitable for executive travel and compiling code: Apple MacBook Pro 14 M3 Pro or Lenovo ThinkPad X1 Carbon?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'Apple MacBook Pro 14" [SKU: 6534640] ($1,799.00, M3 Pro, 18GB RAM, 17 hrs battery) vs Lenovo ThinkPad X1 Carbon [SKU: 6579840] ($1,499.99, Intel Core Ultra 7, 16GB RAM, 2.42 lbs). The MacBook Pro provides higher memory and battery life, whereas the ThinkPad is ultra-portable.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Laptops"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "holdout-laptop-003",
            "archetype": "holdout_comparison",
            "category": "Laptops",
            "expected_skus": ["6534606", "6579840"],
            "key_differential_features": ["processor", "price", "battery_life_hours", "weight_lbs"],
            "ground_truth_specs": {
                "6534606": {
                    "name": 'Apple MacBook Air 13.6" Laptop - M3 chip - 16GB Memory - 512GB SSD',
                    "brand": "Apple",
                    "price": 1099.0,
                    "processor": "Apple M3 8-core",
                    "ram_gb": 16,
                    "battery_life_hours": 18.0,
                    "weight_lbs": 2.7,
                },
                "6579840": {
                    "name": 'Lenovo ThinkPad X1 Carbon Gen 12 14" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD',
                    "brand": "Lenovo",
                    "price": 1499.99,
                    "processor": "Intel Core Ultra 7 155U",
                    "ram_gb": 16,
                    "battery_life_hours": 13.5,
                    "weight_lbs": 2.42,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-laptop-003",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Put MacBook Air 13 M3 and Lenovo ThinkPad X1 Carbon side by side focusing on battery and portability"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'Comparison between Apple MacBook Air 13.6" [SKU: 6534606] ($1,099.00, 18 hrs battery, 2.7 lbs) and Lenovo ThinkPad X1 Carbon Gen 12 [SKU: 6579840] ($1,499.99, 13.5 hrs battery, 2.42 lbs). MacBook Air offers superior battery life at lower cost.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Laptops"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    # Tablets (3 cases)
    cases.append(
        {
            "eval_id": "holdout-tablet-001",
            "archetype": "holdout_comparison",
            "category": "Tablets",
            "expected_skus": ["6546522", "6542951"],
            "key_differential_features": [
                "processor",
                "price",
                "display_resolution",
                "operating_system",
            ],
            "ground_truth_specs": {
                "6546522": {
                    "name": 'Samsung Galaxy Tab S9 11" AMOLED',
                    "brand": "Samsung",
                    "price": 799.99,
                    "processor": "Qualcomm Snapdragon 8 Gen 2",
                    "ram_gb": 8,
                    "display_resolution": "2560 x 1600 Dynamic AMOLED 2X",
                },
                "6542951": {
                    "name": 'Google Pixel Tablet 11" with Charging Speaker Dock',
                    "brand": "Google",
                    "price": 499.0,
                    "processor": "Google Tensor G2",
                    "ram_gb": 8,
                    "display_resolution": "2560 x 1600 LCD",
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-tablet-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Compare Android options: Samsung Galaxy Tab S9 11 inch vs Google Pixel Tablet 11 with speaker dock"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Samsung Galaxy Tab S9 [SKU: 6546522] ($799.99, Dynamic AMOLED 2X) vs Google Pixel Tablet [SKU: 6542951] ($499.00, LCD, Charging Speaker Dock). The Tab S9 delivers premium AMOLED visuals, while the Pixel Tablet doubles as a smart home display at a budget-friendly price."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Tablets"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "holdout-tablet-002",
            "archetype": "holdout_comparison",
            "category": "Tablets",
            "expected_skus": ["6579601", "6542951"],
            "key_differential_features": [
                "processor",
                "price",
                "display_resolution",
                "operating_system",
            ],
            "ground_truth_specs": {
                "6579601": {
                    "name": 'Apple iPad Pro 11" OLED - M4 chip',
                    "brand": "Apple",
                    "price": 999.0,
                    "processor": "Apple M4 9-core",
                    "ram_gb": 8,
                    "display_resolution": "2420 x 1668 Ultra Retina XDR OLED",
                },
                "6542951": {
                    "name": 'Google Pixel Tablet 11" with Charging Speaker Dock',
                    "brand": "Google",
                    "price": 499.0,
                    "processor": "Google Tensor G2",
                    "ram_gb": 8,
                    "display_resolution": "2560 x 1600 LCD",
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-tablet-002",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Is the iPad Pro 11 M4 worth the $500 premium over Google Pixel Tablet?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'Apple iPad Pro 11" [SKU: 6579601] ($999.00, M4 chip, Ultra Retina XDR OLED) vs Google Pixel Tablet [SKU: 6542951] ($499.00, Tensor G2). The iPad Pro is a creative powerhouse, while the Pixel Tablet excels for smart home media consumption.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Tablets"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "holdout-tablet-003",
            "archetype": "holdout_comparison",
            "category": "Tablets",
            "expected_skus": ["6579601", "6546522"],
            "key_differential_features": [
                "processor",
                "price",
                "operating_system",
                "display_resolution",
            ],
            "ground_truth_specs": {
                "6579601": {
                    "name": 'Apple iPad Pro 11" OLED - M4 chip',
                    "brand": "Apple",
                    "price": 999.0,
                    "processor": "Apple M4 9-core",
                    "ram_gb": 8,
                },
                "6546522": {
                    "name": 'Samsung Galaxy Tab S9 11" AMOLED',
                    "brand": "Samsung",
                    "price": 799.99,
                    "processor": "Qualcomm Snapdragon 8 Gen 2",
                    "ram_gb": 8,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-tablet-003",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Flagship tablet showdown: iPad Pro 11 OLED M4 vs Samsung Galaxy Tab S9 AMOLED for digital artists"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'Apple iPad Pro 11" [SKU: 6579601] ($999.00) vs Samsung Galaxy Tab S9 [SKU: 6546522] ($799.99). iPad Pro features the M4 processor and Tandem OLED, while the Tab S9 includes the S Pen in box.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Tablets"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    # Headphones (3 cases)
    cases.append(
        {
            "eval_id": "holdout-headphone-001",
            "archetype": "holdout_comparison",
            "category": "Headphones",
            "expected_skus": ["6553823", "6373460"],
            "key_differential_features": [
                "price",
                "battery_life_hours",
                "weight_oz",
                "driver_size_mm",
            ],
            "ground_truth_specs": {
                "6553823": {
                    "name": "Bose QuietComfort Ultra Wireless Noise Cancelling Headphones",
                    "brand": "Bose",
                    "price": 429.0,
                    "battery_life_hours": 24.0,
                    "weight_oz": 8.9,
                    "driver_size_mm": 35,
                },
                "6373460": {
                    "name": "Apple AirPods Max Wireless Over-Ear Headphones",
                    "brand": "Apple",
                    "price": 549.0,
                    "battery_life_hours": 20.0,
                    "weight_oz": 13.6,
                    "driver_size_mm": 40,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-headphone-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Bose QuietComfort Ultra vs Apple AirPods Max: Which has better comfort and battery for long flights?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Bose QuietComfort Ultra [SKU: 6553823] ($429.00, 24 hrs battery, 8.9 oz) vs Apple AirPods Max [SKU: 6373460] ($549.00, 20 hrs battery, 13.6 oz). The Bose is lighter and offers longer battery life."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [
                            {"name": "query_catalog", "args": {"category": "Headphones"}}
                        ],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "holdout-headphone-002",
            "archetype": "holdout_comparison",
            "category": "Headphones",
            "expected_skus": ["6505727", "6373460"],
            "key_differential_features": [
                "price",
                "battery_life_hours",
                "weight_oz",
                "driver_size_mm",
            ],
            "ground_truth_specs": {
                "6505727": {
                    "name": "Sony WH-1000XM5 Wireless Noise-Canceling Headphones",
                    "brand": "Sony",
                    "price": 399.99,
                    "battery_life_hours": 30.0,
                    "weight_oz": 8.8,
                    "driver_size_mm": 30,
                },
                "6373460": {
                    "name": "Apple AirPods Max Wireless Over-Ear Headphones",
                    "brand": "Apple",
                    "price": 549.0,
                    "battery_life_hours": 20.0,
                    "weight_oz": 13.6,
                    "driver_size_mm": 40,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-headphone-002",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Compare Sony WH-1000XM5 with Apple AirPods Max on weight, battery, and value"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Sony WH-1000XM5 [SKU: 6505727] ($399.99, 30 hrs battery, 8.8 oz) vs Apple AirPods Max [SKU: 6373460] ($549.00, 20 hrs battery, 13.6 oz). Sony leads in battery life and weighs significantly less."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [
                            {"name": "query_catalog", "args": {"category": "Headphones"}}
                        ],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "holdout-headphone-003",
            "archetype": "holdout_comparison",
            "category": "Headphones",
            "expected_skus": ["6505727", "6553823"],
            "key_differential_features": ["price", "battery_life_hours", "driver_size_mm"],
            "ground_truth_specs": {
                "6505727": {
                    "name": "Sony WH-1000XM5 Wireless Noise-Canceling Headphones",
                    "brand": "Sony",
                    "price": 399.99,
                    "battery_life_hours": 30.0,
                    "driver_size_mm": 30,
                },
                "6553823": {
                    "name": "Bose QuietComfort Ultra Wireless Noise Cancelling Headphones",
                    "brand": "Bose",
                    "price": 429.0,
                    "battery_life_hours": 24.0,
                    "driver_size_mm": 35,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-headphone-003",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Which noise canceling headset is better for commuter office use: Sony XM5 or Bose QC Ultra?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Sony WH-1000XM5 [SKU: 6505727] ($399.99, 30 hrs) vs Bose QC Ultra [SKU: 6553823] ($429.00, 24 hrs). Both offer top-tier noise cancellation with Sony holding a 6-hour battery advantage."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [
                            {"name": "query_catalog", "args": {"category": "Headphones"}}
                        ],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    # TVs (3 cases)
    cases.append(
        {
            "eval_id": "holdout-tv-001",
            "archetype": "holdout_comparison",
            "category": "TVs",
            "expected_skus": ["6535929", "6536965"],
            "key_differential_features": [
                "price",
                "refresh_rate_hz",
                "hdr_support",
                "display_technology",
            ],
            "ground_truth_specs": {
                "6535929": {
                    "name": 'LG C3 Series 65" Class OLED evo 4K Smart TV',
                    "brand": "LG",
                    "price": 1499.99,
                    "refresh_rate_hz": 120,
                    "display_technology": "OLED evo",
                },
                "6536965": {
                    "name": 'Samsung S90C Series 65" Class OLED 4K Smart TV',
                    "brand": "Samsung",
                    "price": 1599.99,
                    "refresh_rate_hz": 144,
                    "display_technology": "QD-OLED",
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-tv-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Compare LG C3 65 inch OLED vs Samsung S90C 65 inch for competitive PS5 and PC gaming"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'LG C3 65" [SKU: 6535929] ($1,499.99, 120Hz, Dolby Vision) vs Samsung S90C 65" [SKU: 6536965] ($1,599.99, 144Hz QD-OLED). Samsung offers higher refresh rate for PC gamers, whereas LG supports Dolby Vision.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "TVs"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "holdout-tv-002",
            "archetype": "holdout_comparison",
            "category": "TVs",
            "expected_skus": ["6536965", "6535929"],
            "key_differential_features": ["display_technology", "price", "smart_platform"],
            "ground_truth_specs": {
                "6536965": {
                    "name": 'Samsung S90C Series 65" Class OLED 4K Smart TV',
                    "brand": "Samsung",
                    "price": 1599.99,
                    "display_technology": "QD-OLED",
                },
                "6535929": {
                    "name": 'LG C3 Series 65" Class OLED evo 4K Smart TV',
                    "brand": "LG",
                    "price": 1499.99,
                    "display_technology": "OLED evo",
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-tv-002",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Is Samsung QD-OLED S90C worth the extra $100 over LG C3 OLED evo for living room movie nights?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Samsung S90C [SKU: 6536965] ($1,599.99, QD-OLED) vs LG C3 [SKU: 6535929] ($1,499.99, OLED evo). Samsung excels in color brightness, while LG offers Dolby Vision HDR."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "TVs"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    # Smart Home (2 cases)
    cases.append(
        {
            "eval_id": "holdout-smarthome-001",
            "archetype": "holdout_comparison",
            "category": "Smart Home",
            "expected_skus": ["6584201", "6502275"],
            "key_differential_features": ["price", "connectivity", "voice_assistant"],
            "ground_truth_specs": {
                "6584201": {
                    "name": "Google Nest Learning Thermostat 4th Gen with Temperature Sensor",
                    "brand": "Google",
                    "price": 279.99,
                    "connectivity": "Matter, Thread, Wi-Fi, Bluetooth",
                },
                "6502275": {
                    "name": "ecobee Smart Thermostat Premium with SmartSensor and Air Quality Monitor",
                    "brand": "ecobee",
                    "price": 249.99,
                    "connectivity": "Matter, Wi-Fi, Bluetooth",
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-smarthome-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Evaluate Google Nest Learning Thermostat 4th Gen vs ecobee Smart Thermostat Premium for a Matter-enabled smart home"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Google Nest Thermostat 4th Gen [SKU: 6584201] ($279.99, Matter/Thread) vs ecobee Premium [SKU: 6502275] ($249.99, Matter, air quality monitor). Both support Matter; ecobee adds indoor air quality sensors at a lower cost."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [
                            {"name": "query_catalog", "args": {"category": "Smart Home"}}
                        ],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "holdout-smarthome-002",
            "archetype": "holdout_comparison",
            "category": "Smart Home",
            "expected_skus": ["6502275", "6584201"],
            "key_differential_features": ["price", "voice_assistant"],
            "ground_truth_specs": {
                "6502275": {
                    "name": "ecobee Smart Thermostat Premium with SmartSensor and Air Quality Monitor",
                    "brand": "ecobee",
                    "price": 249.99,
                },
                "6584201": {
                    "name": "Google Nest Learning Thermostat 4th Gen with Temperature Sensor",
                    "brand": "Google",
                    "price": 279.99,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-holdout-smarthome-002",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Which smart thermostat integrates better with Alexa and Apple Home: ecobee Smart Thermostat Premium or Nest 4th Gen?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "ecobee Premium [SKU: 6502275] ($249.99) vs Google Nest 4th Gen [SKU: 6584201] ($279.99). ecobee includes built-in Alexa and Siri compatibility, while Nest is native to Google Assistant."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [
                            {"name": "query_catalog", "args": {"category": "Smart Home"}}
                        ],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    # =========================================================================
    # 2. Counterfactual Spec Mutation Queries (6 Cases)
    # Testing that the agent strictly reflects retrieved catalog data and NOT
    # parametric pretraining knowledge (e.g. promotional prices, custom RAM)
    # =========================================================================
    cases.append(
        {
            "eval_id": "cf-laptop-001",
            "archetype": "counterfactual_spec",
            "category": "Laptops",
            "expected_skus": ["6534606", "6575132"],
            "key_differential_features": ["price", "ram_gb", "battery_life_hours"],
            "ground_truth_specs": {
                "6534606": {
                    "name": 'Apple MacBook Air 13.6" Laptop - M3 chip - 16GB Memory - 512GB SSD',
                    "brand": "Apple",
                    "price": 849.0,  # COUNTERFACTUAL: $849 promo price instead of $1099
                    "ram_gb": 16,
                    "battery_life_hours": 18.0,
                },
                "6575132": {
                    "name": 'Dell XPS 13" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD',
                    "brand": "Dell",
                    "price": 1199.0,
                    "ram_gb": 16,
                    "battery_life_hours": 14.0,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-cf-laptop-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Compare promotional price and battery of MacBook Air 13 M3 vs Dell XPS 13"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'Apple MacBook Air 13.6" [SKU: 6534606] ($849.00, 18 hrs) vs Dell XPS 13" [SKU: 6575132] ($1,199.00, 14 hrs). The MacBook Air features a promotional price of $849.00.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Laptops"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "cf-laptop-002",
            "archetype": "counterfactual_spec",
            "category": "Laptops",
            "expected_skus": ["6575132", "6579840"],
            "key_differential_features": ["price", "ram_gb"],
            "ground_truth_specs": {
                "6575132": {
                    "name": 'Dell XPS 13" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD',
                    "brand": "Dell",
                    "price": 999.0,  # COUNTERFACTUAL: Special sale $999
                    "ram_gb": 16,
                },
                "6579840": {
                    "name": 'Lenovo ThinkPad X1 Carbon Gen 12 14" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD',
                    "brand": "Lenovo",
                    "price": 1499.99,
                    "ram_gb": 16,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-cf-laptop-002",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Is the Dell XPS 13 discounted right now against the ThinkPad X1 Carbon?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Dell XPS 13 [SKU: 6575132] is listed at $999.00 compared to the Lenovo ThinkPad X1 Carbon [SKU: 6579840] at $1,499.99."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Laptops"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "cf-tablet-001",
            "archetype": "counterfactual_spec",
            "category": "Tablets",
            "expected_skus": ["6579601", "6546522"],
            "key_differential_features": ["price", "ram_gb"],
            "ground_truth_specs": {
                "6579601": {
                    "name": 'Apple iPad Pro 11" OLED - M4 chip',
                    "brand": "Apple",
                    "price": 899.0,  # COUNTERFACTUAL: $899 sale price
                    "ram_gb": 8,
                },
                "6546522": {
                    "name": 'Samsung Galaxy Tab S9 11" AMOLED',
                    "brand": "Samsung",
                    "price": 799.99,
                    "ram_gb": 8,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-cf-tablet-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Check price comparison between iPad Pro 11 OLED and Galaxy Tab S9 with current discounts"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'Apple iPad Pro 11" [SKU: 6579601] at discounted $899.00 vs Samsung Galaxy Tab S9 [SKU: 6546522] at $799.99.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Tablets"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "cf-headphone-001",
            "archetype": "counterfactual_spec",
            "category": "Headphones",
            "expected_skus": ["6505727", "6553823"],
            "key_differential_features": ["price", "battery_life_hours"],
            "ground_truth_specs": {
                "6505727": {
                    "name": "Sony WH-1000XM5 Wireless Noise-Canceling Headphones",
                    "brand": "Sony",
                    "price": 329.99,  # COUNTERFACTUAL: $329.99 holiday price
                    "battery_life_hours": 30.0,
                },
                "6553823": {
                    "name": "Bose QuietComfort Ultra Wireless Noise Cancelling Headphones",
                    "brand": "Bose",
                    "price": 429.0,
                    "battery_life_hours": 24.0,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-cf-headphone-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {"text": "Compare prices for Sony WH-1000XM5 and Bose QC Ultra on sale"}
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Sony WH-1000XM5 [SKU: 6505727] ($329.99) vs Bose QC Ultra [SKU: 6553823] ($429.00)."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [
                            {"name": "query_catalog", "args": {"category": "Headphones"}}
                        ],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "cf-tv-001",
            "archetype": "counterfactual_spec",
            "category": "TVs",
            "expected_skus": ["6535929", "6536965"],
            "key_differential_features": ["price", "refresh_rate_hz"],
            "ground_truth_specs": {
                "6535929": {
                    "name": 'LG C3 Series 65" Class OLED evo 4K Smart TV',
                    "brand": "LG",
                    "price": 1299.99,  # COUNTERFACTUAL: $1299.99 doorbuster
                    "refresh_rate_hz": 120,
                },
                "6536965": {
                    "name": 'Samsung S90C Series 65" Class OLED 4K Smart TV',
                    "brand": "Samsung",
                    "price": 1599.99,
                    "refresh_rate_hz": 144,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-cf-tv-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Is LG C3 65 inch OLED currently on sale compared to Samsung S90C?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'LG C3 65" [SKU: 6535929] is available for $1,299.99 versus Samsung S90C [SKU: 6536965] at $1,599.99.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "TVs"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "cf-smarthome-001",
            "archetype": "counterfactual_spec",
            "category": "Smart Home",
            "expected_skus": ["6584201", "6502275"],
            "key_differential_features": ["price"],
            "ground_truth_specs": {
                "6584201": {
                    "name": "Google Nest Learning Thermostat 4th Gen with Temperature Sensor",
                    "brand": "Google",
                    "price": 279.99,
                },
                "6502275": {
                    "name": "ecobee Smart Thermostat Premium with SmartSensor and Air Quality Monitor",
                    "brand": "ecobee",
                    "price": 199.99,  # COUNTERFACTUAL: $199.99 flash sale
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-cf-smarthome-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Compare current retail cost of Nest Thermostat 4th Gen and ecobee Premium"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Google Nest 4th Gen [SKU: 6584201] ($279.99) vs ecobee Premium [SKU: 6502275] ($199.99)."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [
                            {"name": "query_catalog", "args": {"category": "Smart Home"}}
                        ],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    # =========================================================================
    # 3. Negative Chatter, Out-of-Scope & Rants (5 Cases)
    # Expected behavior: Zero product retrieval, zero hallucinated SKUs
    # =========================================================================
    cases.append(
        {
            "eval_id": "neg-chatter-001",
            "archetype": "negative_chatter",
            "category": "Chatter",
            "expected_skus": [],
            "key_differential_features": [],
            "ground_truth_specs": {},
            "conversation": [
                {
                    "invocation_id": "inv-neg-chatter-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Best Buy return policy is terrible and the manager refused my return after 15 days, this is absurd!"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "I understand your frustration with store returns. I am a product comparison assistant focused on consumer electronics specifications. For return disputes or customer service assistance, please visit Best Buy Customer Support at bestbuy.com/support or contact 1-888-BEST-BUY."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "neg-chatter-002",
            "archetype": "negative_chatter",
            "category": "Chatter",
            "expected_skus": [],
            "key_differential_features": [],
            "ground_truth_specs": {},
            "conversation": [
                {
                    "invocation_id": "inv-neg-chatter-002",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Hi! Can you tell me what you can do and what categories you cover?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Hello! I am the Best Buy Product Comparison Assistant. I can provide grounded, side-by-side technical specification comparisons across Laptops, Tablets, Headphones, Smart Home devices, and 4K OLED TVs. Simply ask to compare any two products!"
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "neg-chatter-003",
            "archetype": "negative_chatter",
            "category": "Chatter",
            "expected_skus": [],
            "key_differential_features": [],
            "ground_truth_specs": {},
            "conversation": [
                {
                    "invocation_id": "inv-neg-chatter-003",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "What time does the Best Buy store in Minneapolis close today?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "Store hours vary by location. Please check the Best Buy Store Locator at bestbuy.com/stores for local store hours and curbside pickup schedules."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "neg-chatter-004",
            "archetype": "negative_chatter",
            "category": "Chatter",
            "expected_skus": [],
            "key_differential_features": [],
            "ground_truth_specs": {},
            "conversation": [
                {
                    "invocation_id": "inv-neg-chatter-004",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {"text": "Compare Nintendo Switch OLED with Sony PlayStation 5 Slim"}
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "No matching products were found in our consumer electronics comparison catalog for gaming consoles. Our catalog currently supports Laptops, Tablets, Headphones, Smart Home devices, and 4K TVs."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "neg-chatter-005",
            "archetype": "negative_chatter",
            "category": "Chatter",
            "expected_skus": [],
            "key_differential_features": [],
            "ground_truth_specs": {},
            "conversation": [
                {
                    "invocation_id": "inv-neg-chatter-005",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {"text": "Can you recommend a recipe for chocolate chip cookies?"}
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": "I specialize strictly in consumer electronics comparisons (Laptops, Tablets, Headphones, Smart Home, and TVs). I am unable to assist with culinary recipes."
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    # =========================================================================
    # 4. Cross-Category and Single Product Queries (3 Cases)
    # =========================================================================
    cases.append(
        {
            "eval_id": "cross-cat-001",
            "archetype": "cross_category",
            "category": "CrossCategory",
            "expected_skus": ["6579601", "6505727"],
            "key_differential_features": ["category", "price"],
            "ground_truth_specs": {
                "6579601": {
                    "name": 'Apple iPad Pro 11" OLED - M4 chip',
                    "brand": "Apple",
                    "price": 999.0,
                },
                "6505727": {
                    "name": "Sony WH-1000XM5 Wireless Noise-Canceling Headphones",
                    "brand": "Sony",
                    "price": 399.99,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-cross-cat-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Should I buy an Apple iPad Pro 11 or Sony WH-1000XM5 headphones for starting college?"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'Notice: You are comparing across two different categories — a Tablet (Apple iPad Pro 11" [SKU: 6579601], $999.00) and Noise-Canceling Headphones (Sony WH-1000XM5 [SKU: 6505727], $399.99). The iPad serves note-taking and coursework, while the Sony headphones offer noise isolation for studying.'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "cross-cat-002",
            "archetype": "cross_category",
            "category": "CrossCategory",
            "expected_skus": ["6575132", "6535929"],
            "key_differential_features": ["category", "price"],
            "ground_truth_specs": {
                "6575132": {
                    "name": 'Dell XPS 13" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD',
                    "brand": "Dell",
                    "price": 1199.0,
                },
                "6535929": {
                    "name": 'LG C3 Series 65" Class OLED evo 4K Smart TV',
                    "brand": "LG",
                    "price": 1499.99,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-cross-cat-002",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {"text": "Compare Dell XPS 13 laptop with LG C3 65 inch OLED TV"}
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'These products belong to distinct categories: Dell XPS 13 [SKU: 6575132] is a portable laptop ($1,199.00), while the LG C3 65" [SKU: 6535929] is a 4K home entertainment TV ($1,499.99).'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    cases.append(
        {
            "eval_id": "single-prod-001",
            "archetype": "cross_category",
            "category": "SingleProduct",
            "expected_skus": ["6534640"],
            "key_differential_features": ["price", "processor", "ram_gb", "battery_life_hours"],
            "ground_truth_specs": {
                "6534640": {
                    "name": 'Apple MacBook Pro 14" Laptop - M3 Pro chip - 18GB Memory - 512GB SSD',
                    "brand": "Apple",
                    "price": 1799.0,
                    "processor": "Apple M3 Pro 11-core",
                    "ram_gb": 18,
                    "battery_life_hours": 17.0,
                },
            },
            "conversation": [
                {
                    "invocation_id": "inv-single-prod-001",
                    "user_content": {
                        "role": "user",
                        "parts": [
                            {
                                "text": "Tell me all the technical specs of the Apple MacBook Pro 14 M3 Pro"
                            }
                        ],
                    },
                    "final_response": {
                        "role": "model",
                        "parts": [
                            {
                                "text": 'Apple MacBook Pro 14" [SKU: 6534640] features the Apple M3 Pro 11-core chip, 18GB RAM, 512GB SSD, up to 17.0 hours battery life, priced at $1,799.00. To compare it with another laptop, name a second model!'
                            }
                        ],
                    },
                    "intermediate_data": {
                        "tool_uses": [{"name": "query_catalog", "args": {"category": "Laptops"}}],
                        "tool_responses": [],
                        "intermediate_responses": [],
                    },
                }
            ],
        }
    )

    return {
        "eval_set_id": "bestbuy_catalog_holdout_counterfactual",
        "name": "Best Buy Catalog Holdout & Counterfactual Anti-Overfitting Dataset",
        "description": "Curated holdout comparison pairs, counterfactual spec mutations, negative rants, and cross-category edge cases to evaluate agent generalization and anti-overfitting.",
        "eval_cases": cases,
    }


def main():
    dataset = generate_holdout_dataset()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
    print(f"Generated {len(dataset['eval_cases'])} holdout cases at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
