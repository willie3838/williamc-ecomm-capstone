import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ComparisonTable } from '../components/ComparisonTable';
import { mockComparisonResponse } from './mockData';

describe('ComparisonTable', () => {
  it('renders table headers with product names and brands', () => {
    render(
      <ComparisonTable
        products={mockComparisonResponse.products}
        matrix={mockComparisonResponse.comparison_matrix}
      />
    );

    expect(screen.getByText(/MacBook Air 13.6/i)).toBeInTheDocument();
    expect(screen.getByText(/XPS 13 13.4/i)).toBeInTheDocument();
    expect(screen.getByText('Apple')).toBeInTheDocument();
    expect(screen.getByText('Dell')).toBeInTheDocument();
  });

  it('renders all comparison matrix feature rows', () => {
    render(
      <ComparisonTable
        products={mockComparisonResponse.products}
        matrix={mockComparisonResponse.comparison_matrix}
      />
    );

    expect(screen.getByText('Price')).toBeInTheDocument();
    expect(screen.getByText('RAM Memory')).toBeInTheDocument();
    expect(screen.getByText('Storage')).toBeInTheDocument();
    expect(screen.getByText('Battery Life')).toBeInTheDocument();
    expect(screen.getByText('Weight')).toBeInTheDocument();
  });

  it('highlights winning product specifications with badge indicator', () => {
    render(
      <ComparisonTable
        products={mockComparisonResponse.products}
        matrix={mockComparisonResponse.comparison_matrix}
      />
    );

    // Battery life winner is MacBook (6534606)
    const winnerBadges = screen.getAllByLabelText(/superior specification/i);
    expect(winnerBadges.length).toBeGreaterThan(0);
  });

  it('handles empty matrix gracefully', () => {
    render(
      <ComparisonTable
        products={mockComparisonResponse.products}
        matrix={[]}
      />
    );

    expect(screen.getByText(/No detailed comparison specs available/i)).toBeInTheDocument();
  });

  it('renders null when products array is empty', () => {
    const { container } = render(
      <ComparisonTable products={[]} matrix={[]} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('formats boolean and missing spec values cleanly', () => {
    const customMatrix = [
      {
        feature: 'Backlit Keyboard',
        values: {
          '6534606': true,
          '6573822': false,
        },
      },
      {
        feature: 'Touch Screen',
        values: {
          '6534606': null,
          '6573822': 'Yes',
        },
      },
    ];

    render(
      <ComparisonTable
        products={mockComparisonResponse.products}
        matrix={customMatrix}
      />
    );

    expect(screen.getByText('Backlit Keyboard')).toBeInTheDocument();
    expect(screen.getAllByText('Yes').length).toBe(2);
    expect(screen.getByText('No')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('highlights multiple winning products in 3+ comparisons with ties via winner_skus', () => {
    const threeProducts = [
      { ...mockComparisonResponse.products[0], sku: 'SKU-1', name: 'Product 1' },
      { ...mockComparisonResponse.products[1], sku: 'SKU-2', name: 'Product 2' },
      {
        ...mockComparisonResponse.products[0],
        sku: 'SKU-3',
        name: 'Product 3',
        brand: 'HP',
      },
    ];

    const tiedMatrix = [
      {
        feature: 'Refresh Rate',
        values: {
          'SKU-1': '120 Hz',
          'SKU-2': '120 Hz',
          'SKU-3': '60 Hz',
        },
        winner_sku: null,
        winner_skus: ['SKU-1', 'SKU-2'],
      },
    ];

    render(<ComparisonTable products={threeProducts} matrix={tiedMatrix} />);

    // Both SKU-1 and SKU-2 should display Winner badges (total of 2)
    const winnerBadges = screen.getAllByLabelText(/superior specification/i);
    expect(winnerBadges).toHaveLength(2);
  });

  it('renders no winner badge when tied across all products with empty winner_skus', () => {
    const threeProducts = [
      { ...mockComparisonResponse.products[0], sku: 'SKU-1', name: 'Product 1' },
      { ...mockComparisonResponse.products[1], sku: 'SKU-2', name: 'Product 2' },
      {
        ...mockComparisonResponse.products[0],
        sku: 'SKU-3',
        name: 'Product 3',
        brand: 'HP',
      },
    ];

    const neutralMatrix = [
      {
        feature: 'Refresh Rate',
        values: {
          'SKU-1': '120 Hz',
          'SKU-2': '120 Hz',
          'SKU-3': '120 Hz',
        },
        winner_sku: null,
        winner_skus: [],
      },
    ];

    render(<ComparisonTable products={threeProducts} matrix={neutralMatrix} />);

    const winnerBadges = screen.queryAllByLabelText(/superior specification/i);
    expect(winnerBadges).toHaveLength(0);
  });
});
