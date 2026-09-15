import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ProductCard } from '../components/ProductCard';
import { mockMacBook } from './mockData';

describe('ProductCard', () => {
  it('renders product details correctly', () => {
    render(<ProductCard product={mockMacBook} />);

    expect(screen.getByText(mockMacBook.name)).toBeInTheDocument();
    expect(screen.getByText('Apple')).toBeInTheDocument();
    expect(screen.getByText('$1,099.00')).toBeInTheDocument();
    expect(screen.getByText(/4.8/i)).toBeInTheDocument();
    expect(screen.getByText(/1,420 reviews/i)).toBeInTheDocument();
    expect(screen.getByText(/In Stock/i)).toBeInTheDocument();
  });

  it('renders SKU citation chip inside product card', () => {
    render(<ProductCard product={mockMacBook} />);
    expect(screen.getByText(/SKU: 6534606/i)).toBeInTheDocument();
  });

  it('renders out-of-stock badge when in_stock is false', () => {
    render(<ProductCard product={{ ...mockMacBook, in_stock: false }} />);
    expect(screen.getByText(/Out of Stock/i)).toBeInTheDocument();
  });
});
