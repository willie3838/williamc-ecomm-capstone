import { ComparisonResponse, ProductSpec } from '../types/comparison';

export const mockMacBook: ProductSpec = {
  sku: '6534606',
  name: 'Apple - MacBook Air 13.6" Laptop - M3 chip - 8GB Memory - 256GB SSD - Midnight',
  brand: 'Apple',
  category: 'Laptops',
  price: 1099.0,
  rating: 4.8,
  review_count: 1420,
  specifications: {
    'Screen Size': '13.6 inches',
    Processor: 'Apple M3 8-core',
    'RAM Memory': '8 GB',
    Storage: '256 GB SSD',
    'Battery Life': '18 hours',
    Weight: '2.7 pounds',
  },
  url: 'https://www.techbuy.com/site/sku/6534606.p',
  image_url: 'https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6534/6534606_sd.jpg',
  in_stock: true,
};

export const mockDellXPS: ProductSpec = {
  sku: '6573822',
  name: 'Dell - XPS 13 13.4" OLED Touch-Screen Laptop - Intel Core Ultra 7 - 16GB Memory - 512GB SSD - Platinum',
  brand: 'Dell',
  category: 'Laptops',
  price: 1399.0,
  rating: 4.5,
  review_count: 320,
  specifications: {
    'Screen Size': '13.4 inches',
    Processor: 'Intel Core Ultra 7 155H',
    'RAM Memory': '16 GB',
    Storage: '512 GB SSD',
    'Battery Life': '13 hours',
    Weight: '2.6 pounds',
  },
  url: 'https://www.techbuy.com/site/sku/6573822.p',
  image_url: 'https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6573/6573822_sd.jpg',
  in_stock: true,
};

export const mockComparisonResponse: ComparisonResponse = {
  summary:
    'The MacBook Air M3 offers unmatched battery life (18 hrs) and silent fanless performance at $1,099. The Dell XPS 13 provides double the RAM (16GB) and storage (512GB) with an OLED display at $1,399.',
  products: [mockMacBook, mockDellXPS],
  comparison_matrix: [
    {
      feature: 'Price',
      values: {
        '6534606': '$1,099.00',
        '6573822': '$1,399.00',
      },
      winner_sku: '6534606',
    },
    {
      feature: 'RAM Memory',
      values: {
        '6534606': '8 GB',
        '6573822': '16 GB',
      },
      winner_sku: '6573822',
    },
    {
      feature: 'Storage',
      values: {
        '6534606': '256 GB SSD',
        '6573822': '512 GB SSD',
      },
      winner_sku: '6573822',
    },
    {
      feature: 'Battery Life',
      values: {
        '6534606': '18 hours',
        '6573822': '13 hours',
      },
      winner_sku: '6534606',
    },
    {
      feature: 'Weight',
      values: {
        '6534606': '2.7 lbs',
        '6573822': '2.6 lbs',
      },
      winner_sku: '6573822',
    },
  ],
  citations: [
    {
      sku: '6534606',
      url: 'https://www.techbuy.com/site/sku/6534606.p',
      description: 'Grounded in BigQuery catalog: Apple MacBook Air M3',
    },
    {
      sku: '6573822',
      url: 'https://www.techbuy.com/site/sku/6573822.p',
      description: 'Grounded in BigQuery catalog: Dell XPS 13 OLED',
    },
  ],
  recommendations:
    'Choose the MacBook Air M3 for battery endurance, portability, and value. Choose the Dell XPS 13 if you require 16GB RAM for multitasking and prefer Windows.',
  latency_ms: 1280.45,
};
