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
});
