import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CitationChip } from '../components/CitationChip';

describe('CitationChip', () => {
  it('renders SKU text with format [SKU: {sku}]', () => {
    render(<CitationChip sku="6534606" />);
    expect(screen.getByText(/SKU: 6534606/i)).toBeInTheDocument();
  });

  it('links to canonical BestBuy.com SKU product page by default', () => {
    render(<CitationChip sku="6534606" />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'https://www.bestbuy.com/site/sku/6534606.p');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('supports custom URL when provided', () => {
    render(<CitationChip sku="6534606" url="https://custom.bestbuy.com/p" />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'https://custom.bestbuy.com/p');
  });

  it('renders description or tooltip when provided', () => {
    render(
      <CitationChip
        sku="6534606"
        description="Verified catalog record in BigQuery"
      />
    );
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('title', 'Verified catalog record in BigQuery');
  });
});
