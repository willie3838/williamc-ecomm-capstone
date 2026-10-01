import { describe, it, expect } from 'vitest';
import { CATALOG_PRODUCTS, searchCatalogProducts, getCatalogProducts } from '../data/catalogProducts';

describe('CATALOG_PRODUCTS specifications and image URLs', () => {
  it('contains exactly 40 catalog products', () => {
    expect(CATALOG_PRODUCTS).toHaveLength(40);
  });

  it('has unique SKU identifiers across all products', () => {
    const skus = CATALOG_PRODUCTS.map((p) => p.sku);
    const uniqueSkus = new Set(skus);
    expect(uniqueSkus.size).toBe(40);
  });

  it('has valid non-empty string values for core metadata on every product', () => {
    for (const product of CATALOG_PRODUCTS) {
      expect(product.sku).toBeTruthy();
      expect(product.name).toBeTruthy();
      expect(product.brand).toBeTruthy();
      expect(product.category).toBeTruthy();
      expect(product.price).toBeGreaterThan(0);
      expect(product.specifications).toBeDefined();
    }
  });

  it('has verified Best Buy CDN image_url for all 40 products', () => {
    const cdnPrefix = 'https://pisces.bbystatic.com/image2/BestBuy_US/images/products/';

    for (const product of CATALOG_PRODUCTS) {
      expect(product.image_url, `Product SKU ${product.sku} has missing image_url`).toBeDefined();
      expect(typeof product.image_url).toBe('string');
      expect(
        product.image_url?.startsWith(cdnPrefix),
        `Product SKU ${product.sku} image_url (${product.image_url}) does not start with Best Buy CDN prefix ${cdnPrefix}`
      ).toBe(true);
      expect(product.image_url?.length).toBeGreaterThan(cdnPrefix.length);
    }
  });

  it('covers all five canonical categories with at least one product', () => {
    const categories = new Set(CATALOG_PRODUCTS.map((p) => p.category));
    expect(categories).toContain('Laptops');
    expect(categories).toContain('Tablets');
    expect(categories).toContain('Headphones');
    expect(categories).toContain('Smart Home');
    expect(categories).toContain('TVs');
  });
});

describe('searchCatalogProducts', () => {
  it('returns all products when query is empty or whitespace with no category', () => {
    const emptyResults = searchCatalogProducts('');
    expect(emptyResults).toHaveLength(40);

    const whitespaceResults = searchCatalogProducts('   ');
    expect(whitespaceResults).toHaveLength(40);
  });

  it('returns all category products when query is empty or whitespace with a category', () => {
    const laptopResults = searchCatalogProducts('', 'Laptops');
    const expectedLaptops = getCatalogProducts('Laptops');
    expect(laptopResults).toHaveLength(expectedLaptops.length);
    expect(laptopResults.every((p) => p.category === 'Laptops')).toBe(true);

    const tvResults = searchCatalogProducts('  ', 'TVs');
    expect(tvResults).toHaveLength(getCatalogProducts('TVs').length);
    expect(tvResults.every((p) => p.category === 'TVs')).toBe(true);
  });

  it('filters by exact SKU match', () => {
    const results = searchCatalogProducts('6534606');
    expect(results).toHaveLength(1);
    expect(results[0].sku).toBe('6534606');
    expect(results[0].name).toContain('MacBook Air');
  });

  it('filters by brand name case-insensitively', () => {
    const results = searchCatalogProducts('apple');
    expect(results.length).toBeGreaterThan(0);
    expect(results.some((p) => p.brand === 'Apple')).toBe(true);
    expect(
      results.every(
        (p) =>
          p.brand.toLowerCase().includes('apple') ||
          p.name.toLowerCase().includes('apple') ||
          JSON.stringify(p.specifications).toLowerCase().includes('apple')
      )
    ).toBe(true);
  });

  it('filters by specification values like processor or resolution', () => {
    const m3Results = searchCatalogProducts('M3 chip');
    expect(m3Results.length).toBeGreaterThan(0);
    expect(m3Results.some((p) => p.sku === '6534606')).toBe(true);

    const snapdragonResults = searchCatalogProducts('Snapdragon X Elite');
    expect(snapdragonResults.length).toBeGreaterThan(0);
    expect(snapdragonResults.some((p) => p.sku === '6581910')).toBe(true);
  });

  it('performs multi-word token matching across different fields', () => {
    // "Dell 16GB" -> Brand is Dell, spec RAM is 16
    const results = searchCatalogProducts('Dell 16GB');
    expect(results.length).toBeGreaterThan(0);
    expect(results.some((p) => p.brand === 'Dell' && p.specifications.ram_gb === 16)).toBe(true);

    // "Sony 120Hz" -> Sony TVs with 120Hz refresh rate
    const sonyResults = searchCatalogProducts('Sony 120Hz');
    expect(sonyResults.length).toBeGreaterThan(0);
    expect(sonyResults.some((p) => p.brand === 'Sony' && p.specifications.refresh_rate_hz === 120)).toBe(true);
  });

  it('respects category constraint when searching', () => {
    // Search for Apple in Tablets only
    const results = searchCatalogProducts('Apple', 'Tablets');
    expect(results.length).toBeGreaterThan(0);
    expect(results.every((p) => p.category === 'Tablets')).toBe(true);
    expect(results.some((p) => p.sku === '6579601')).toBe(true); // iPad Pro
    // Should NOT contain MacBook
    expect(results.some((p) => p.category === 'Laptops')).toBe(false);
  });

  it('returns empty array when query does not match any products', () => {
    const results = searchCatalogProducts('NonExistentProductZ999X');
    expect(results).toHaveLength(0);
  });
});

