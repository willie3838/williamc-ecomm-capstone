import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
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

  it('renders selection toggle button when selectable is true', () => {
    const onToggle = vi.fn();
    render(
      <ProductCard
        product={mockMacBook}
        selectable={true}
        isSelected={false}
        onToggleSelect={onToggle}
      />
    );

    const checkbox = screen.getByRole('checkbox', {
      name: new RegExp(`Select ${mockMacBook.name} for comparison`, 'i'),
    });
    expect(checkbox).toBeInTheDocument();
    expect(checkbox).toHaveAttribute('aria-checked', 'false');

    checkbox.click();
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith(mockMacBook);
  });

  it('indicates selected state with aria-checked and active styles when isSelected is true', () => {
    render(
      <ProductCard
        product={mockMacBook}
        selectable={true}
        isSelected={true}
      />
    );

    const checkbox = screen.getByRole('checkbox', {
      name: new RegExp(`Select ${mockMacBook.name} for comparison`, 'i'),
    });
    expect(checkbox).toHaveAttribute('aria-checked', 'true');
  });

  it('does not render selection checkbox when selectable is false or omitted', () => {
    render(<ProductCard product={mockMacBook} />);
    expect(
      screen.queryByRole('checkbox', {
        name: new RegExp(`Select ${mockMacBook.name} for comparison`, 'i'),
      })
    ).not.toBeInTheDocument();
  });

  it('calls onViewDetails when View at TechBuy button is clicked', () => {
    const onViewDetails = vi.fn();
    render(<ProductCard product={mockMacBook} onViewDetails={onViewDetails} />);

    const viewBtn = screen.getByRole('button', { name: /view at techbuy/i });
    expect(viewBtn).toBeInTheDocument();

    viewBtn.click();
    expect(onViewDetails).toHaveBeenCalledTimes(1);
    expect(onViewDetails).toHaveBeenCalledWith(mockMacBook);
  });
});

