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

  it('renders TechBuy Retailers branding, hero text, and All Categories catalog by default', () => {
    renderWithClient(<App />);

    expect(screen.getByText('TECHBUY RETAILERS')).toBeInTheDocument();
    expect(
      screen.getByText('Compare Consumer Electronics Side-by-Side')
    ).toBeInTheDocument();
    // Default view should now be All Categories Catalog
    expect(screen.getByText(/All Categories Catalog/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 40 verified SKUs/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6534606/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6505727/i)).toBeInTheDocument();
    expect(screen.queryByText('Popular Product Comparisons')).not.toBeInTheDocument();
    expect(screen.queryByText('MacBook Air M3 vs Dell XPS 13')).not.toBeInTheDocument();
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

  it('returns to All Categories catalog when TECHBUY RETAILERS header logo is clicked', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    // Navigate into a comparison view via SearchBar
    const searchInput = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(searchInput, {
      target: { value: 'Compare MacBook Air and Dell XPS 13' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^compare$/i }));

    await waitFor(() => {
      expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    });

    // Click TECHBUY RETAILERS logo to return home
    const logoBtn = screen.getByRole('button', { name: /techbuy retailers/i });
    fireEvent.click(logoBtn);

    expect(screen.getByText(/All Categories Catalog/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 40 verified SKUs/i)).toBeInTheDocument();
    expect(screen.queryByText('Side-by-Side Specification Matrix')).not.toBeInTheDocument();

    // Also verify returning home from category SKU browse view (e.g. Laptops)
    fireEvent.click(screen.getByRole('button', { name: /^laptops$/i }));
    expect(screen.getByText(/Laptops Catalog/i)).toBeInTheDocument();

    fireEvent.click(logoBtn);
    expect(screen.getByText(/All Categories Catalog/i)).toBeInTheDocument();
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

    // Verify tray shows ready state (2/5)
    expect(screen.getByText('Ready to compare (2/5)')).toBeInTheDocument();

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
    const searchInput = screen.getByRole('textbox', {
      name: /natural language product comparison query/i,
    });
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
    const searchInput = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(searchInput, {
      target: { value: 'MacBook Air M3 vs Dell XPS 13' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^compare$/i }));

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

    const searchInput = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(searchInput, {
      target: { value: 'MacBook Air M3 vs Dell XPS 13' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^compare$/i }));

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

  it('auto-populates compared SKU tags in SearchBar whenever any comparison completes, enabling immediate follow-up', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    // Perform initial comparison via search
    const searchInput = screen.getByRole('textbox', {
      name: /natural language product comparison query/i,
    });
    fireEvent.change(searchInput, {
      target: { value: 'MacBook Air M3 vs Dell XPS 13' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^compare$/i }));

    await waitFor(() => {
      expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    });

    // Verify SearchBar search form now displays auto-populated SKU chips
    const searchForm = screen.getByRole('search');
    expect(searchForm).toHaveTextContent(/SKU:\s*6534606/i);
    expect(searchForm).toHaveTextContent(/SKU:\s*6573822/i);

    // Verify placeholder now invites follow-up constraints
    expect(searchInput).toHaveAttribute(
      'placeholder',
      'Add follow-up requirements (e.g., "only price", "good for gaming", "battery life")...'
    );

    // Enter follow-up requirement: "good for gaming"
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);
    fireEvent.change(searchInput, { target: { value: 'good for gaming' } });
    fireEvent.submit(searchForm);

    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(2);
    });

    const followUpCallArgs = vi.mocked(compareProducts).mock.calls[1][0];
    expect(followUpCallArgs.query).toContain('User Focus / Follow-up: good for gaming');
    expect(followUpCallArgs.query).toContain('[SKU: 6534606]');
    expect(followUpCallArgs.query).toContain('[SKU: 6573822]');
  });

  it('renders SKU tags immediately in SearchBar during category multi-select without raw query text', async () => {
    renderWithClient(<App />);

    // Enter Laptops category catalog
    const laptopsBtn = screen.getByRole('button', { name: /^laptops$/i });
    fireEvent.click(laptopsBtn);

    expect(screen.getByText(/Laptops Catalog/i)).toBeInTheDocument();

    // Select first laptop (MacBook Air SKU: 6534606)
    const macbookCheckbox = screen.getByRole('checkbox', {
      name: /Select Apple MacBook Air 13.6" Laptop/i,
    });
    fireEvent.click(macbookCheckbox);

    // SearchBar search form should now display SKU: 6534606 tag chip immediately
    const searchForm = screen.getByRole('search');
    expect(searchForm).toHaveTextContent(/SKU:\s*6534606/i);
    expect(searchForm).toHaveTextContent(/Apple MacBook Air/i);

    // Textbox should NOT contain raw query text like "Compare Apple MacBook Air..."
    const searchInput = screen.getByRole('textbox', {
      name: /natural language product comparison query/i,
    }) as HTMLInputElement;
    expect(searchInput.value).toBe('');
    expect(searchInput).toHaveAttribute(
      'placeholder',
      'Add follow-up requirements (e.g., "only price", "good for gaming", "battery life")...'
    );

    // Select second laptop (Dell XPS 13 SKU: 6575132)
    const dellCheckbox = screen.getByRole('checkbox', {
      name: /Select Dell XPS 13"/i,
    });
    fireEvent.click(dellCheckbox);

    // SearchBar now shows both SKU chips
    expect(searchForm).toHaveTextContent(/SKU:\s*6534606/i);
    expect(searchForm).toHaveTextContent(/SKU:\s*6575132/i);
    expect(searchInput.value).toBe('');

    // Remove first tag via SearchBar remove tag button
    const removeBtn = screen.getByRole('button', {
      name: /remove tag for Apple MacBook Air 13.6" Laptop/i,
    });
    fireEvent.click(removeBtn);

    // First tag should be gone, second tag remains
    expect(searchForm).not.toHaveTextContent(/SKU:\s*6534606/i);
    expect(searchForm).toHaveTextContent(/SKU:\s*6575132/i);

    // Checkbox in catalog should reflect unselection
    expect(macbookCheckbox).not.toBeChecked();
    expect(dellCheckbox).toBeChecked();
  });

  it('filters catalog products in browsing view via live catalog search input and clear button', () => {
    renderWithClient(<App />);

    // Check placeholder
    const liveSearchInput = screen.getByPlaceholderText(
      'Search products by name, brand, SKU, or spec to compare...'
    );
    expect(liveSearchInput).toBeInTheDocument();

    // Default shows 40 products
    expect(screen.getByText(/40 of 40 matching/i)).toBeInTheDocument();

    // Type "Bose" into live search input
    fireEvent.change(liveSearchInput, { target: { value: 'Bose' } });

    // Should filter to Bose products
    expect(screen.getByText(/Bose QuietComfort Ultra/i)).toBeInTheDocument();
    expect(screen.queryByText(/Dell XPS 13/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 of 40 matching/i)).toBeInTheDocument();

    // Clear button should appear and reset search
    const clearBtn = screen.getByRole('button', { name: /clear catalog search/i });
    expect(clearBtn).toBeInTheDocument();
    fireEvent.click(clearBtn);

    expect(screen.getByText(/40 of 40 matching/i)).toBeInTheDocument();
    expect(screen.getByText(/Dell XPS 13/i)).toBeInTheDocument();
  });

  it('renders "+ Add Product to Compare Against" in Compared Products header and adds product', async () => {
    vi.mocked(compareProducts).mockResolvedValue(mockComparisonResponse);

    renderWithClient(<App />);

    const searchInput = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(searchInput, {
      target: { value: 'Compare MacBook Air and Dell XPS 13' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^compare$/i }));

    await waitFor(() => {
      expect(screen.getByText('Compared Products')).toBeInTheDocument();
    });

    const addCompareBtn = screen.getByRole('button', {
      name: /\+ Add Product to Compare Against/i,
    });
    expect(addCompareBtn).toBeInTheDocument();
    fireEvent.click(addCompareBtn);

    const popoverSearch = screen.getByPlaceholderText(/search product by name, brand, sku/i);
    expect(popoverSearch).toBeInTheDocument();

    fireEvent.change(popoverSearch, { target: { value: 'Lenovo ThinkPad' } });
    const lenovoOption = screen.getByText(/Lenovo ThinkPad X1 Carbon/i);
    fireEvent.click(lenovoOption);

    // Should trigger new comparison query with Lenovo included
    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(2);
    });
  });

  it('allows multiselecting up to 5 products in category browser and executing 5-way comparison', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce({
      ...mockComparisonResponse,
      products: [
        mockComparisonResponse.products[0],
        mockComparisonResponse.products[1],
        { ...mockComparisonResponse.products[0], sku: 'SKU003', name: 'Laptop Model 3' },
        { ...mockComparisonResponse.products[0], sku: 'SKU004', name: 'Laptop Model 4' },
        { ...mockComparisonResponse.products[0], sku: 'SKU005', name: 'Laptop Model 5' },
      ],
    });

    renderWithClient(<App />);

    // Click Laptops category pill
    fireEvent.click(screen.getByRole('button', { name: /laptops/i }));
    expect(screen.getByText(/Laptops Catalog/i)).toBeInTheDocument();

    // Select 5 products
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes.length).toBeGreaterThanOrEqual(5);

    for (let i = 0; i < 5; i++) {
      fireEvent.click(checkboxes[i]);
    }

    // Verify tray shows ready state (5/5)
    expect(screen.getByText('Ready to compare (5/5)')).toBeInTheDocument();

    // Click Compare Selected (5)
    const compareSelectedBtn = screen.getByRole('button', {
      name: /compare 5 selected products/i,
    });
    fireEvent.click(compareSelectedBtn);

    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(1);
    });

    const callArgs = vi.mocked(compareProducts).mock.calls[0][0];
    expect(callArgs.category).toBe('Laptops');
    expect(callArgs.query).toContain('Compare the following products:');
  });
});




