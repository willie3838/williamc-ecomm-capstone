import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ProductDetailsModal } from '../components/ProductDetailsModal';
import { mockMacBook } from './mockData';
import { ProductSpec } from '../types/comparison';

describe('ProductDetailsModal', () => {
  it('does not render when isOpen is false', () => {
    render(
      <ProductDetailsModal
        product={mockMacBook}
        isOpen={false}
        onClose={vi.fn()}
      />
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not render when product is null', () => {
    render(
      <ProductDetailsModal
        product={null}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders product details, specs, price, stock status, and rating when open', () => {
    render(
      <ProductDetailsModal
        product={mockMacBook}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();

    // Title and Brand
    expect(screen.getByText(mockMacBook.name)).toBeInTheDocument();
    expect(screen.getByText('Apple')).toBeInTheDocument();
    expect(screen.getByText('Laptops')).toBeInTheDocument();

    // Price & Stock
    expect(screen.getByText('$1,099.00')).toBeInTheDocument();
    expect(screen.getByText(/In Stock/i)).toBeInTheDocument();

    // Rating
    expect(screen.getByText('4.8')).toBeInTheDocument();
    expect(screen.getByText(/1,420 customer reviews/i)).toBeInTheDocument();

    // Specs
    expect(screen.getByText('Apple M3 8-core')).toBeInTheDocument();
    expect(screen.getByText('8 GB')).toBeInTheDocument();
    expect(screen.getByText('18 hours')).toBeInTheDocument();
  });

  it('renders out-of-stock badge when in_stock is false', () => {
    const outOfStockProduct: ProductSpec = {
      ...mockMacBook,
      in_stock: false,
    };

    render(
      <ProductDetailsModal
        product={outOfStockProduct}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText(/Out of Stock/i)).toBeInTheDocument();
  });

  it('calls onClose when close button (X) is clicked', () => {
    const onClose = vi.fn();
    render(
      <ProductDetailsModal
        product={mockMacBook}
        isOpen={true}
        onClose={onClose}
      />
    );

    const closeBtn = screen.getByRole('button', { name: /close product details/i });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when clicking outside modal backdrop', () => {
    const onClose = vi.fn();
    render(
      <ProductDetailsModal
        product={mockMacBook}
        isOpen={true}
        onClose={onClose}
      />
    );

    const backdrop = screen.getByTestId('modal-backdrop');
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Escape key is pressed', () => {
    const onClose = vi.fn();
    render(
      <ProductDetailsModal
        product={mockMacBook}
        isOpen={true}
        onClose={onClose}
      />
    );

    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders selection action button and calls onSelectForCompare when clicked', () => {
    const onSelect = vi.fn();
    render(
      <ProductDetailsModal
        product={mockMacBook}
        isOpen={true}
        onClose={vi.fn()}
        onSelectForCompare={onSelect}
        isSelectedForCompare={false}
      />
    );

    const compareBtn = screen.getByRole('button', { name: /add to comparison/i });
    expect(compareBtn).toBeInTheDocument();

    fireEvent.click(compareBtn);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(mockMacBook);
  });

  it('shows selected state on compare button when isSelectedForCompare is true', () => {
    render(
      <ProductDetailsModal
        product={mockMacBook}
        isOpen={true}
        onClose={vi.fn()}
        onSelectForCompare={vi.fn()}
        isSelectedForCompare={true}
      />
    );

    expect(screen.getByRole('button', { name: /remove from comparison/i })).toBeInTheDocument();
  });

  it('handles image loading error gracefully by displaying fallback package icon', () => {
    render(
      <ProductDetailsModal
        product={mockMacBook}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    const img = screen.getByAltText(mockMacBook.name);
    fireEvent.error(img);

    expect(screen.getByText(/TechBuy Retailers Verified Catalog SKU/i)).toBeInTheDocument();
  });
});
