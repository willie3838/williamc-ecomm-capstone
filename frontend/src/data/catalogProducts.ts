import { ProductSpec } from '../types/comparison';
import catalogSeedJson from './catalog_seed.json';

/**
 * Full 10,040-product catalog grounded in fde-bestbuy-sandbox-dev-508321.catalog.products.
 * Indices 0..39 preserve the 40 canonical benchmark SKUs; indices 40..10039 contain
 * 10,000 verified Best Buy products (2,008 total SKUs per category across 5 categories).
 */
export const CATALOG_PRODUCTS: ProductSpec[] = catalogSeedJson as unknown as ProductSpec[];

function buildSearchBlob(product: ProductSpec): string {
  const specParts: string[] = [];
  if (product.specifications) {
    for (const [key, val] of Object.entries(product.specifications)) {
      if (val === null || val === undefined) continue;
      specParts.push(key.replace(/_/g, ' '));
      specParts.push(String(val));
      if (typeof val === 'number') {
        if (key.endsWith('_gb')) specParts.push(`${val}gb`);
        if (key.endsWith('_hz')) specParts.push(`${val}hz`);
        if (key.endsWith('_hours')) specParts.push(`${val}h`, `${val}hours`);
        if (key.endsWith('_lbs')) specParts.push(`${val}lbs`);
        if (key.endsWith('_in') || key.endsWith('_inches')) {
          specParts.push(`${val}"`, `${val}in`, `${val}inch`);
        }
        if (key.endsWith('_oz')) specParts.push(`${val}oz`);
        if (key.endsWith('_mm')) specParts.push(`${val}mm`);
      }
    }
  }

  return [
    product.name,
    product.brand,
    product.sku,
    product.category ?? '',
    specParts.join(' '),
  ]
    .join(' ')
    .toLowerCase();
}

/**
 * Returns all catalog SKUs when category is null/undefined, or filters SKUs matching the specified category on demand.
 */
export function getCatalogProducts(category?: string | null): ProductSpec[] {
  if (!category) {
    return CATALOG_PRODUCTS;
  }
  const categoryLower = category.toLowerCase();
  return CATALOG_PRODUCTS.filter(
    (product) => (product.category ?? '').toLowerCase() === categoryLower
  );
}

/**
 * Searches the catalog products matching query across name, brand, SKU, category, and specifications directly on demand.
 * Supports case-insensitive multi-word token matching and optional category filtering.
 */
export function searchCatalogProducts(
  query: string,
  category?: string | null
): ProductSpec[] {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) {
    return getCatalogProducts(category);
  }

  const tokens = trimmed.split(/\s+/).filter(Boolean);
  const categoryLower = category ? category.toLowerCase() : null;

  const results: ProductSpec[] = [];
  for (let i = 0; i < CATALOG_PRODUCTS.length; i++) {
    const product = CATALOG_PRODUCTS[i];
    if (categoryLower && (product.category ?? '').toLowerCase() !== categoryLower) {
      continue;
    }
    const searchBlob = buildSearchBlob(product);
    let matchesAll = true;
    for (let t = 0; t < tokens.length; t++) {
      if (!searchBlob.includes(tokens[t])) {
        matchesAll = false;
        break;
      }
    }
    if (matchesAll) {
      results.push(product);
    }
  }
  return results;
}
