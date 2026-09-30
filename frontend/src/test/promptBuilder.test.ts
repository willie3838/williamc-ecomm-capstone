import { describe, it, expect } from 'vitest';
import { buildComparisonPrompt } from '../utils/promptBuilder';
import { mockMacBook, mockDellXPS } from './mockData';

describe('promptBuilder', () => {
  it('returns raw query string trimmed when no tagged products are provided', () => {
    expect(buildComparisonPrompt([], 'Compare MacBook Air and Dell XPS')).toBe(
      'Compare MacBook Air and Dell XPS'
    );
    expect(buildComparisonPrompt([], '  hello world  ')).toBe('hello world');
    expect(buildComparisonPrompt([])).toBe('');
  });

  it('formats tagged products with all their attributes and appends custom user follow-up prompt', () => {
    const prompt = buildComparisonPrompt(
      [mockMacBook, mockDellXPS],
      'only price and battery life'
    );

    // Assert contains SKU tags and names
    expect(prompt).toContain(`[SKU: ${mockMacBook.sku}]`);
    expect(prompt).toContain(mockMacBook.name);
    expect(prompt).toContain(`[SKU: ${mockDellXPS.sku}]`);
    expect(prompt).toContain(mockDellXPS.name);

    // Assert contains prices
    expect(prompt).toContain(`$${mockMacBook.price}`);
    expect(prompt).toContain(`$${mockDellXPS.price}`);

    // Assert contains specifications
    expect(prompt).toContain('Apple M3 8-core');
    expect(prompt).toContain('Intel Core Ultra 7');

    // Assert contains user follow-up prompt
    expect(prompt).toContain('User Focus / Follow-up: only price and battery life');
  });

  it('provides a grounded default comparison instruction when follow-up prompt is empty or whitespace', () => {
    const prompt = buildComparisonPrompt([mockMacBook, mockDellXPS], '   ');

    expect(prompt).toContain(`[SKU: ${mockMacBook.sku}]`);
    expect(prompt).toContain(`[SKU: ${mockDellXPS.sku}]`);
    expect(prompt).toContain('Compare specifications, trade-offs, and recommend the best option.');
  });

  it('handles products with empty or missing specifications gracefully', () => {
    const partialProduct = {
      sku: '1234567',
      name: 'Generic Headphones',
      brand: 'AudioCo',
      price: 99.99,
      specifications: {},
      in_stock: true,
    };

    const prompt = buildComparisonPrompt([partialProduct], 'good for gym');
    expect(prompt).toContain('[SKU: 1234567]');
    expect(prompt).toContain('Generic Headphones');
    expect(prompt).toContain('$99.99');
    expect(prompt).toContain('User Focus / Follow-up: good for gym');
  });

  it('keeps total prompt length bounded well under 4000 characters for multiple products', () => {
    const prompt = buildComparisonPrompt(
      [mockMacBook, mockDellXPS],
      'Detailed comparison of battery and display quality for software development'
    );
    expect(prompt.length).toBeLessThan(4000);
    expect(prompt.length).toBeGreaterThan(100);
  });
});
