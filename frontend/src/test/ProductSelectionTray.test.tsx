import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ProductSelectionTray } from '../components/ProductSelectionTray';
import { mockMacBook, mockDellXPS } from './mockData';

describe('ProductSelectionTray', () => {
  it('renders nothing when selectedProducts is empty', () => {
    const { container } = render(
      <ProductSelectionTray
        selectedProducts={[]}
        onRemoveProduct={vi.fn()}
        onClearSelection={vi.fn()}
        onCompare={vi.fn()}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders selected count and item chips when products are selected', () => {
    render(
      <ProductSelectionTray
        selectedProducts={[mockMacBook]}
        onRemoveProduct={vi.fn()}
        onClearSelection={vi.fn()}
        onCompare={vi.fn()}
      />
    );

    expect(screen.getByText('Selected for Comparison')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText(/Select at least 1 more product/i)).toBeInTheDocument();
    expect(screen.getByText(mockMacBook.name)).toBeInTheDocument();
  });


  it('disables Compare Selected button when fewer than 2 products are selected', () => {
    const onCompare = vi.fn();
    render(
      <ProductSelectionTray
        selectedProducts={[mockMacBook]}
        onRemoveProduct={vi.fn()}
        onClearSelection={vi.fn()}
        onCompare={onCompare}
      />
    );

    const compareBtn = screen.getByRole('button', {
      name: /compare 1 selected products/i,
    });
    expect(compareBtn).toBeDisabled();

    fireEvent.click(compareBtn);
    expect(onCompare).not.toHaveBeenCalled();
  });

  it('enables Compare Selected button and triggers onCompare callback with selected products when 2+ items are selected', () => {
    const onCompare = vi.fn();
    render(
      <ProductSelectionTray
        selectedProducts={[mockMacBook, mockDellXPS]}
        onRemoveProduct={vi.fn()}
        onClearSelection={vi.fn()}
        onCompare={onCompare}
      />
    );

    expect(screen.getByText('Ready to compare (2/4)')).toBeInTheDocument();

    const compareBtn = screen.getByRole('button', {
      name: /compare 2 selected products/i,
    });
    expect(compareBtn).not.toBeDisabled();

    fireEvent.click(compareBtn);
    expect(onCompare).toHaveBeenCalledTimes(1);
    expect(onCompare).toHaveBeenCalledWith([mockMacBook, mockDellXPS]);
  });

  it('calls onRemoveProduct when remove (X) button on a product chip is clicked', () => {
    const onRemove = vi.fn();
    render(
      <ProductSelectionTray
        selectedProducts={[mockMacBook, mockDellXPS]}
        onRemoveProduct={onRemove}
        onClearSelection={vi.fn()}
        onCompare={vi.fn()}
      />
    );

    const removeMacBookBtn = screen.getByRole('button', {
      name: new RegExp(`Remove ${mockMacBook.name} from selection`, 'i'),
    });
    fireEvent.click(removeMacBookBtn);

    expect(onRemove).toHaveBeenCalledTimes(1);
    expect(onRemove).toHaveBeenCalledWith(mockMacBook.sku);
  });

  it('calls onClearSelection when Clear button is clicked', () => {
    const onClear = vi.fn();
    render(
      <ProductSelectionTray
        selectedProducts={[mockMacBook, mockDellXPS]}
        onRemoveProduct={vi.fn()}
        onClearSelection={onClear}
        onCompare={vi.fn()}
      />
    );

    const clearBtn = screen.getByRole('button', {
      name: /clear all selected products/i,
    });
    fireEvent.click(clearBtn);

    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('calls onClearSelection when Escape key is pressed', () => {
    const onClear = vi.fn();
    render(
      <ProductSelectionTray
        selectedProducts={[mockMacBook, mockDellXPS]}
        onRemoveProduct={vi.fn()}
        onClearSelection={onClear}
        onCompare={vi.fn()}
      />
    );

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});

