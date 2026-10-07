import { ProductSpec, TaggedSku } from '../types/comparison';

/**
 * Builds an attribute-grounded comparison prompt combining tagged SKU data with
 * optional user follow-up questions / prompts (e.g., 'only price' or 'good for gaming').
 *
 * @param taggedSkus - Array of products tagged for comparison
 * @param userPrompt - Optional user follow-up prompt or query filter
 * @returns Grounded comparison prompt string
 */
export function buildComparisonPrompt(
  taggedSkus: (ProductSpec | TaggedSku)[],
  userPrompt?: string | null
): string {
  const trimmedPrompt = userPrompt?.trim() || '';

  // If no tagged SKUs, return raw user prompt as-is
  if (!taggedSkus || taggedSkus.length === 0) {
    return trimmedPrompt;
  }

  const lines: string[] = [];
  lines.push('Compare the following products:');

  taggedSkus.forEach((prod, index) => {
    const brandStr = prod.brand ? ` (${prod.brand})` : '';
    const priceStr =
      prod.price !== undefined && prod.price !== null ? ` - $${prod.price}` : '';
    lines.push(`Product ${index + 1}: ${prod.name}${brandStr} [SKU: ${prod.sku}]${priceStr}`);

    if (prod.specifications && Object.keys(prod.specifications).length > 0) {
      lines.push('  Specifications:');
      for (const [key, val] of Object.entries(prod.specifications)) {
        if (val !== null && val !== undefined && val !== '') {
          lines.push(`  * ${key}: ${val}`);
        }
      }
    }
  });

  if (trimmedPrompt) {
    lines.push(`User Focus / Follow-up: ${trimmedPrompt}`);
  } else {
    lines.push('Compare specifications, trade-offs, and recommend the best option.');
  }

  return lines.join('\n');
}
