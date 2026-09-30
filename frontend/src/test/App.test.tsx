import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from '../App';
import { mockComparisonResponse } from './mockData';

// Mock the client API
vi.mock('../api/client', () => ({
  compareProducts: vi.fn(),
  checkHealth: vi.fn(),
}));

import { compareProducts } from '../api/client';

const renderWithClient = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
};

describe('App Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders TechBuy Retailers branding, hero text, and sample comparisons by default', () => {
    renderWithClient(<App />);

    expect(screen.getByText('TECHBUY RETAILERS')).toBeInTheDocument();
    expect(
      screen.getByText('Compare Consumer Electronics Side-by-Side')
    ).toBeInTheDocument();
    expect(screen.getByText('MacBook Air M3 vs Dell XPS 13')).toBeInTheDocument();
    expect(
      screen.getByText('Sony WH-1000XM5 vs Bose QC Ultra')
    ).toBeInTheDocument();
  });

  it('executes search and displays comparison results, matrix, and citations', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    const searchInput = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(searchInput, {
      target: { value: 'Compare MacBook Air and Dell XPS 13' },
    });

    const compareBtn = screen.getByRole('button', { name: /^compare$/i });
    fireEvent.click(compareBtn);

    // Verify comparison response elements render
    await waitFor(() => {
      expect(screen.getByText(/The MacBook Air M3 offers unmatched battery life/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    expect(screen.getByText('Compared Products')).toBeInTheDocument();
    expect(screen.getByText('Verified SKU Grounding & Citations')).toBeInTheDocument();
  });

  it('triggers comparison when a sample card is clicked', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    const sampleBtn = screen.getByText('MacBook Air M3 vs Dell XPS 13').closest('button');
    expect(sampleBtn).not.toBeNull();
    fireEvent.click(sampleBtn!);

    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(1);
    });
  });

  it('displays error state when comparison request fails', async () => {
    vi.mocked(compareProducts).mockRejectedValue(
      new Error('Catalog service temporarily unavailable')
    );

    renderWithClient(<App />);

    const searchInput = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(searchInput, {
      target: { value: 'Compare non-existent products' },
    });

    const compareBtn = screen.getByRole('button', { name: /^compare$/i });
    fireEvent.click(compareBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(screen.getByText('Comparison Failed')).toBeInTheDocument();
    expect(
      screen.getByText('Catalog service temporarily unavailable')
    ).toBeInTheDocument();
  });

  it('shows all catalog SKUs when All Categories pill is clicked and filters relevant SKUs when a category pill is clicked', () => {
    renderWithClient(<App />);

    // Click "All Categories" pill -> should show all 40 catalog SKUs
    const allCategoriesBtn = screen.getByRole('button', { name: /all categories/i });
    fireEvent.click(allCategoriesBtn);

    expect(screen.getByText(/All Categories Catalog/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 40 verified SKUs/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6534606/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6505727/i)).toBeInTheDocument();

    // Click "Headphones" pill -> should show only the 8 Headphones SKUs
    const headphonesBtn = screen.getByRole('button', { name: /headphones/i });
    fireEvent.click(headphonesBtn);

    expect(screen.getByText(/Headphones Catalog/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 8 verified SKUs/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6505727/i)).toBeInTheDocument();
    expect(screen.queryByText(/SKU: 6534606/i)).not.toBeInTheDocument();
  });

  it('returns to the homepage when TECHBUY RETAILERS header logo is clicked', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    // Navigate into a comparison view
    const sampleBtn = screen.getByText('MacBook Air M3 vs Dell XPS 13').closest('button');
    fireEvent.click(sampleBtn!);

    await waitFor(() => {
      expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    });

    // Click TECHBUY RETAILERS logo to return home
    const logoBtn = screen.getByRole('button', { name: /techbuy retailers/i });
    fireEvent.click(logoBtn);

    expect(screen.getByText('Popular Product Comparisons')).toBeInTheDocument();
    expect(screen.queryByText('Side-by-Side Specification Matrix')).not.toBeInTheDocument();

    // Also verify returning home from category SKU browse view
    fireEvent.click(screen.getByRole('button', { name: /^laptops$/i }));
    expect(screen.getByText(/Laptops Catalog/i)).toBeInTheDocument();

    fireEvent.click(logoBtn);
    expect(screen.getByText('Popular Product Comparisons')).toBeInTheDocument();
    expect(screen.queryByText(/Laptops Catalog/i)).not.toBeInTheDocument();
  });

  it('allows multiselecting products in category SKU browser and executing comparison via selection tray', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    // 1. Enter Laptops category catalog
    const laptopsBtn = screen.getByRole('button', { name: /^laptops$/i });
    fireEvent.click(laptopsBtn);

    expect(screen.getByText(/Laptops Catalog/i)).toBeInTheDocument();

    // 2. Select first laptop (MacBook Air)
    const macbookCheckbox = screen.getByRole('checkbox', {
      name: /Select Apple MacBook Air 13.6" Laptop/i,
    });
    fireEvent.click(macbookCheckbox);

    // Verify selection tray appears with 1 item and disabled Compare button
    expect(screen.getByText('Selected for Comparison')).toBeInTheDocument();
    expect(screen.getByText(/Select at least 1 more product/i)).toBeInTheDocument();

    // 3. Select second laptop (Dell XPS 13)
    const dellCheckbox = screen.getByRole('checkbox', {
      name: /Select Dell XPS 13"/i,
    });
    fireEvent.click(dellCheckbox);

    // Verify tray shows ready state (2/4)
    expect(screen.getByText('Ready to compare (2/4)')).toBeInTheDocument();

    // 4. Click Compare Selected
    const compareSelectedBtn = screen.getByRole('button', {
      name: /compare 2 selected products/i,
    });
    fireEvent.click(compareSelectedBtn);

    // 5. Verify comparison is triggered with implicitly built prompt containing tagged SKUs
    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(1);
    });

    const callArgs = vi.mocked(compareProducts).mock.calls[0][0];
    expect(callArgs.query).toContain('Apple MacBook Air 13.6" Laptop');
    expect(callArgs.query).toContain('Dell XPS 13"');
    expect(callArgs.query).toContain('[SKU: 6534606]');
    expect(callArgs.query).toContain('[SKU: 6575132]');
    expect(callArgs.category).toBe('Laptops');

    // Matrix should be displayed
    await waitFor(() => {
      expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    });

    // Verify SKU tags are visible inside the SearchBar form
    const searchForm = screen.getByRole('search');
    expect(searchForm).toHaveTextContent(/SKU:\s*6534606/i);
    expect(searchForm).toHaveTextContent(/SKU:\s*6575132/i);

    // 6. Test submitting user follow-up prompt (e.g., "only price") retains tagged SKUs
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);
    const searchInput = screen.getByRole('textbox');
    fireEvent.change(searchInput, { target: { value: 'only price' } });
    fireEvent.submit(screen.getByRole('search'));

    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(2);
    });
    const followUpArgs = vi.mocked(compareProducts).mock.calls[1][0];
    expect(followUpArgs.query).toContain('User Focus / Follow-up: only price');
    expect(followUpArgs.query).toContain('[SKU: 6534606]');
    expect(followUpArgs.query).toContain('[SKU: 6575132]');
  });

  it('opens ProductDetailsModal when View at TechBuy button on ProductCard is clicked and closes upon dismissing', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    // Perform a search to populate compared products
    const sampleBtn = screen.getByText('MacBook Air M3 vs Dell XPS 13').closest('button');
    fireEvent.click(sampleBtn!);

    await waitFor(() => {
      expect(screen.getByText('Compared Products')).toBeInTheDocument();
    });

    // Find "View at TechBuy" buttons
    const viewButtons = screen.getAllByRole('button', { name: /view at techbuy/i });
    expect(viewButtons.length).toBeGreaterThan(0);

    // Click the first "View at TechBuy" button (MacBook Air)
    fireEvent.click(viewButtons[0]);

    // Modal dialog should now be visible with MacBook specs and details
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText('Verified Product Specifications')).toBeInTheDocument();
    expect(screen.getByText('Apple M3 8-core')).toBeInTheDocument();

    // Close the modal via Close button
    const closeBtn = screen.getByRole('button', { name: /close product details/i });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens ProductDetailsModal when SKU CitationChip is clicked', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    const sampleBtn = screen.getByText('MacBook Air M3 vs Dell XPS 13').closest('button');
    fireEvent.click(sampleBtn!);

    await waitFor(() => {
      expect(screen.getByText('Verified SKU Grounding & Citations')).toBeInTheDocument();
    });

    // Find citation chips in the page
    const citationBtns = screen.getAllByRole('button', {
      name: /view product details for sku 6534606/i,
    });
    expect(citationBtns.length).toBeGreaterThan(0);
    fireEvent.click(citationBtns[0]);

    // Modal dialog should open displaying MacBook Air details
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText('Apple M3 8-core')).toBeInTheDocument();

    // Dismiss using Escape key
    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});


