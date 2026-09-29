import { describe, it, expect } from 'vitest';
import { CATALOG_PRODUCTS } from '../data/catalogProducts';

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
