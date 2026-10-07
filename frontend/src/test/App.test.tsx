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

  const tagTwoDefaultLaptopsAndSubmit = (followUpText?: string) => {
    const macbookCheckbox = screen.getByRole('checkbox', {
      name: /Select Apple MacBook Air 13.6" Laptop/i,
    });
    const dellCheckbox = screen.getByRole('checkbox', {
      name: /Select Dell XPS 13"/i,
    });
    fireEvent.click(macbookCheckbox);
    fireEvent.click(dellCheckbox);

    if (followUpText) {
      const searchInput = screen.getByRole('textbox', {
        name: /natural language product comparison query/i,
      });
      fireEvent.change(searchInput, { target: { value: followUpText } });
    }

    const compareBtn = screen.getByRole('button', { name: /^compare$/i });
    fireEvent.click(compareBtn);
  };

  it('renders TechBuy Retailers branding, hero text, and All Categories catalog by default', () => {
    renderWithClient(<App />);

    expect(screen.getByText('TECHBUY RETAILERS')).toBeInTheDocument();
    expect(
      screen.getByText('Compare Consumer Electronics Side-by-Side')
    ).toBeInTheDocument();
    // Default view should now be All Categories Catalog
    expect(screen.getByText(/All Categories Catalog/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 10040 verified SKUs/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6534606/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6505727/i)).toBeInTheDocument();
    expect(screen.queryByText('Popular Product Comparisons')).not.toBeInTheDocument();
    expect(screen.queryByText('MacBook Air M3 vs Dell XPS 13')).not.toBeInTheDocument();
  });

  it('blocks raw untagged or 1-product search submissions and requires at least 2 tagged products before comparing', () => {
    renderWithClient(<App />);

    const searchInput = screen.getByRole('textbox', {
      name: /natural language product comparison query/i,
    });
    const compareBtn = screen.getByRole('button', { name: /^compare$/i });

    // 1. 0 products tagged: typing text still keeps Compare disabled and blocks Enter/submit
    expect(compareBtn).toBeDisabled();
    fireEvent.change(searchInput, {
      target: { value: 'Compare MacBook Air and Dell XPS 13' },
    });
    expect(compareBtn).toBeDisabled();
    fireEvent.click(compareBtn);
    fireEvent.submit(screen.getByRole('search'));
    fireEvent.keyDown(searchInput, { key: 'Enter', code: 'Enter', shiftKey: false });
    expect(compareProducts).not.toHaveBeenCalled();

    // 2. 1 product tagged: Compare remains disabled and blocks Enter/submit
    const macbookCheckbox = screen.getByRole('checkbox', {
      name: /Select Apple MacBook Air 13.6" Laptop/i,
    });
    fireEvent.click(macbookCheckbox);
    expect(compareBtn).toBeDisabled();
    fireEvent.click(compareBtn);
    fireEvent.submit(screen.getByRole('search'));
    fireEvent.keyDown(searchInput, { key: 'Enter', code: 'Enter', shiftKey: false });
    expect(compareProducts).not.toHaveBeenCalled();
  });

  it('executes search and displays comparison results, matrix, and citations when 2 products are tagged', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    tagTwoDefaultLaptopsAndSubmit('Compare MacBook Air and Dell XPS 13');

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

    tagTwoDefaultLaptopsAndSubmit('Compare laptops');

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

    // Click "All Categories" pill -> should show all 10040 catalog SKUs
    const allCategoriesBtn = screen.getByRole('button', { name: /all categories/i });
    fireEvent.click(allCategoriesBtn);

    expect(screen.getByText(/All Categories Catalog/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 10040 verified SKUs/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6534606/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6505727/i)).toBeInTheDocument();

    // Click "Headphones" pill -> should show the 2008 Headphones SKUs
    const headphonesBtn = screen.getByRole('button', { name: /headphones/i });
    fireEvent.click(headphonesBtn);

    expect(screen.getByText(/Headphones Catalog/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 2008 verified SKUs/i)).toBeInTheDocument();
    expect(screen.getByText(/SKU: 6505727/i)).toBeInTheDocument();
    expect(screen.queryByText(/SKU: 6534606/i)).not.toBeInTheDocument();
  });

  it('returns to All Categories catalog when TECHBUY RETAILERS header logo is clicked', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    // Navigate into a comparison view via SearchBar with 2 tagged products
    tagTwoDefaultLaptopsAndSubmit('Compare MacBook Air and Dell XPS 13');

    await waitFor(() => {
      expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    });

    // Click TECHBUY RETAILERS logo to return home
    const logoBtn = screen.getByRole('button', { name: /techbuy retailers/i });
    fireEvent.click(logoBtn);

    expect(screen.getByText(/All Categories Catalog/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 10040 verified SKUs/i)).toBeInTheDocument();
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

    // Perform a search with 2 tagged products to populate compared products
    tagTwoDefaultLaptopsAndSubmit('MacBook Air M3 vs Dell XPS 13');

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

    tagTwoDefaultLaptopsAndSubmit('MacBook Air M3 vs Dell XPS 13');

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

  it('retains compared SKU tags in SearchBar whenever any comparison completes, enabling immediate follow-up', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    const searchInput = screen.getByRole('textbox', {
      name: /natural language product comparison query/i,
    });

    // Tag 2 products and perform initial comparison via search
    tagTwoDefaultLaptopsAndSubmit('MacBook Air M3 vs Dell XPS 13');

    await waitFor(() => {
      expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    });

    // Verify SearchBar search form displays the tagged SKU chips
    const searchForm = screen.getByRole('search');
    expect(searchForm).toHaveTextContent(/SKU:\s*6534606/i);
    expect(searchForm).toHaveTextContent(/SKU:\s*6575132/i);

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
    expect(followUpCallArgs.query).toContain('[SKU: 6575132]');
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
      'Select at least 1 more product to compare, or add follow-up requirements (e.g., "only price", "good for gaming", "battery life")...'
    );

    // Select second laptop (Dell XPS 13 SKU: 6575132)
    const dellCheckbox = screen.getByRole('checkbox', {
      name: /Select Dell XPS 13"/i,
    });
    fireEvent.click(dellCheckbox);

    // SearchBar now shows both SKU chips and follow-up placeholder
    expect(searchForm).toHaveTextContent(/SKU:\s*6534606/i);
    expect(searchForm).toHaveTextContent(/SKU:\s*6575132/i);
    expect(searchInput.value).toBe('');
    expect(searchInput).toHaveAttribute(
      'placeholder',
      'Add follow-up requirements (e.g., "only price", "good for gaming", "battery life")...'
    );

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

    // Default shows 10040 products
    expect(screen.getByText(/10040 of 10040 matching/i)).toBeInTheDocument();

    // Type "6553823" (Bose QuietComfort Ultra SKU) into live search input
    fireEvent.change(liveSearchInput, { target: { value: '6553823' } });

    // Should filter to Bose QuietComfort Ultra product
    expect(screen.getByText(/Bose QuietComfort Ultra/i)).toBeInTheDocument();
    expect(screen.queryByText(/Dell XPS 13/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 of 10040 matching/i)).toBeInTheDocument();

    // Clear button should appear and reset search
    const clearBtn = screen.getByRole('button', { name: /clear catalog search/i });
    expect(clearBtn).toBeInTheDocument();
    fireEvent.click(clearBtn);

    expect(screen.getByText(/10040 of 10040 matching/i)).toBeInTheDocument();
    expect(screen.getByText(/Dell XPS 13/i)).toBeInTheDocument();
  });

  it('paginates catalog ProductCard rendering to 40 cards initially and loads more when Load More button is clicked', () => {
    renderWithClient(<App />);

    // Total verified SKU count badge remains 10,040
    expect(screen.getByText(/Showing 10040 verified SKUs/i)).toBeInTheDocument();

    // Only 40 ProductCards are mounted initially
    const initialCheckboxes = screen.getAllByRole('checkbox');
    expect(initialCheckboxes).toHaveLength(40);

    // Load More button should be visible
    const loadMoreBtn = screen.getByRole('button', { name: /load more/i });
    expect(loadMoreBtn).toBeInTheDocument();

    // Clicking Load More renders 40 additional cards (total 80)
    fireEvent.click(loadMoreBtn);
    expect(screen.getAllByRole('checkbox')).toHaveLength(80);
  });

  it('renders "+ Add Product to Compare Against" in Compared Products header and adds product', async () => {
    vi.mocked(compareProducts).mockResolvedValue(mockComparisonResponse);

    renderWithClient(<App />);

    tagTwoDefaultLaptopsAndSubmit('Compare MacBook Air and Dell XPS 13');

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

    // Wait for comparison result to render
    await waitFor(() => {
      expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    });

    // Verify all 5 product cards render with h-full and full-width aligned action buttons
    const viewButtons = screen.getAllByRole('button', { name: /view at techbuy/i });
    expect(viewButtons.length).toBeGreaterThanOrEqual(5);
    viewButtons.slice(0, 5).forEach((btn) => {
      expect(btn.className).toContain('w-full');
      expect(btn.className).toContain('whitespace-nowrap');
    });

    // Verify ComparisonTable sticky column cells are opaque
    const stickyCells = document.querySelectorAll('tbody td.sticky');
    expect(stickyCells.length).toBeGreaterThan(0);
    stickyCells.forEach((cell) => {
      expect(cell.className).not.toContain('bg-inherit');
      const isOpaque = cell.className.includes('bg-white') || cell.className.includes('bg-slate-50');
      expect(isOpaque).toBe(true);
    });
  });

  it('renders ConversationSidebar immediately open to the right after comparison completes and supports toggle', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    const searchInput = screen.getByRole('textbox', {
      name: /natural language product comparison query/i,
    });
    tagTwoDefaultLaptopsAndSubmit('Compare MacBook Air and Dell XPS 13');

    // Wait for comparison to render
    await waitFor(() => {
      expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    });

    // 1. Follow-up chat sidebar should be open immediately
    expect(screen.getByText('Comparison Assistant')).toBeInTheDocument();
    expect(screen.getByText('Ask about these products')).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText('Ask a follow-up question...')
    ).toBeInTheDocument();

    // 2. Close the sidebar via close button
    const closeBtn = screen.getByRole('button', {
      name: /close conversation sidebar/i,
    });
    fireEvent.click(closeBtn);

    // Sidebar should be closed and "Open Follow-up Chat" button appears
    expect(screen.queryByText('Comparison Assistant')).not.toBeInTheDocument();
    const openChatBtn = screen.getByRole('button', {
      name: /open follow-up chat/i,
    });
    expect(openChatBtn).toBeInTheDocument();

    // 3. Re-open via button
    fireEvent.click(openChatBtn);
    expect(screen.getByText('Comparison Assistant')).toBeInTheDocument();

    // 4. Close again and trigger new comparison via search -> should auto-reopen
    fireEvent.click(screen.getByRole('button', { name: /close conversation sidebar/i }));
    expect(screen.queryByText('Comparison Assistant')).not.toBeInTheDocument();

    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);
    fireEvent.change(searchInput, {
      target: { value: 'Compare battery life' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^compare$/i }));

    await waitFor(() => {
      expect(screen.getByText('Comparison Assistant')).toBeInTheDocument();
    });
  });

  it('preserves existing compared products when adding a product via SearchBar "+ Add Product to Compare"', async () => {
    vi.mocked(compareProducts).mockResolvedValue(mockComparisonResponse);

    renderWithClient(<App />);

    // 1. Run initial comparison of 2 products (MacBook Air 6534606 & Dell XPS 6575132)
    tagTwoDefaultLaptopsAndSubmit('Compare MacBook Air and Dell XPS 13');

    await waitFor(() => {
      expect(screen.getByText('Compared Products')).toBeInTheDocument();
    });

    // Verify initial tagged products in SearchBar
    expect(screen.getByText('SKU: 6534606')).toBeInTheDocument();
    expect(screen.getByText('SKU: 6575132')).toBeInTheDocument();

    // 2. Click "+ Add Product to Compare" inside SearchBar
    const addBtn = screen.getByLabelText('Add product to compare');
    fireEvent.click(addBtn);

    // 3. Search and select a 3rd product in the picker (e.g. Lenovo ThinkPad)
    const pickerSearch = screen.getByPlaceholderText(/search products by name, brand, or sku/i);
    fireEvent.change(pickerSearch, { target: { value: 'Lenovo' } });

    const lenovoOption = screen.getByText(/Lenovo ThinkPad X1 Carbon/i);
    fireEvent.click(lenovoOption);

    // 4. Verify that existing 2 products are STILL preserved and Lenovo was added (now 3 tagged products)
    const taggedRow = screen.getByTestId('tagged-products-row');
    expect(taggedRow).toHaveTextContent('SKU: 6534606');
    expect(taggedRow).toHaveTextContent('SKU: 6575132');
    expect(taggedRow).toHaveTextContent(/Lenovo ThinkPad X1 Carbon/i);

    // 5. Verify the selection tray also reflects 3 products
    expect(screen.getByText(/Ready to compare \(3\/5\)/i)).toBeInTheDocument();
  });

  it('preserves existing compared products when adding a product via autocomplete', async () => {
    vi.mocked(compareProducts).mockResolvedValue(mockComparisonResponse);

    renderWithClient(<App />);

    tagTwoDefaultLaptopsAndSubmit('Compare MacBook Air and Dell XPS 13');

    await waitFor(() => {
      expect(screen.getByText('Compared Products')).toBeInTheDocument();
    });

    // Type into main search input to trigger autocomplete dropdown
    const textarea = screen.getByPlaceholderText(/add follow-up requirements/i);
    fireEvent.change(textarea, { target: { value: 'Acer' } });

    const dropdown = screen.getByRole('listbox', { name: /product suggestions/i });
    expect(dropdown).toBeInTheDocument();

    const acerOption = screen.getByText(/Acer Swift Edge/i);
    fireEvent.click(acerOption);

    // Verify existing 2 products are preserved and Acer was added
    const taggedRow = screen.getByTestId('tagged-products-row');
    expect(taggedRow).toHaveTextContent('SKU: 6534606');
    expect(taggedRow).toHaveTextContent('SKU: 6575132');
    expect(taggedRow).toHaveTextContent(/Acer Swift Edge/i);
  });

  it('searches across all categories in "+ Add Product to Compare Against" popover and passes category=null for cross-category comparison', async () => {
    vi.mocked(compareProducts).mockResolvedValue(mockComparisonResponse);

    renderWithClient(<App />);

    // Initial comparison with category "Laptops"
    fireEvent.click(screen.getByRole('button', { name: /laptops/i }));
    tagTwoDefaultLaptopsAndSubmit('Compare MacBook Air and Dell XPS 13');

    await waitFor(() => {
      expect(screen.getByText('Compared Products')).toBeInTheDocument();
    });

    // Open "+ Add Product to Compare Against" popover
    const addCompareBtn = screen.getByRole('button', {
      name: /\+ Add Product to Compare Against/i,
    });
    fireEvent.click(addCompareBtn);

    const popoverSearch = screen.getByPlaceholderText(/search product by name, brand, sku/i);

    // Search for iPad Pro (which is in Tablets category, not Laptops!)
    fireEvent.change(popoverSearch, { target: { value: 'iPad Pro' } });

    // Verify cross-category product (Tablet) is found and visible
    const ipadOption = screen.getByText(/Apple iPad Pro 11" OLED/i);
    expect(ipadOption).toBeInTheDocument();
    fireEvent.click(ipadOption);

    // Verify new comparison request was initiated with category: null (cross-category)
    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(2);
    });

    const secondCallArgs = vi.mocked(compareProducts).mock.calls[1][0];
    expect(secondCallArgs.category).toBeNull();
  });

  it('updates taggedProducts when a new comparison completes with different products', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    tagTwoDefaultLaptopsAndSubmit('Compare MacBook Air and Dell XPS 13');

    await waitFor(() => {
      expect(screen.getByText('Compared Products')).toBeInTheDocument();
      expect(screen.getByText('SKU: 6534606')).toBeInTheDocument();
    });

    // Subsequent comparison completes with headphones (different SKUs)
    const headphoneComparison = {
      ...mockComparisonResponse,
      products: [
        {
          sku: '6573888',
          name: 'Sony WH-1000XM5 Wireless Headphones',
          brand: 'Sony',
          category: 'Headphones',
          price: 399.99,
          specifications: {},
          in_stock: true,
        },
        {
          sku: '6573999',
          name: 'Bose QuietComfort Ultra Headphones',
          brand: 'Bose',
          category: 'Headphones',
          price: 429.99,
          specifications: {},
          in_stock: true,
        },
      ],
    };
    vi.mocked(compareProducts).mockResolvedValueOnce(headphoneComparison);

    const followUpInput = screen.getByPlaceholderText(/add follow-up requirements/i);
    fireEvent.change(followUpInput, {
      target: { value: 'Recommend headphones instead' },
    });
    fireEvent.submit(screen.getByRole('search'));

    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(2);
    });

    await waitFor(() => {
      expect(screen.getByText('SKU: 6573888')).toBeInTheDocument();
      expect(screen.getByText('SKU: 6573999')).toBeInTheDocument();
    });

    // Old SKUs should no longer be tagged
    expect(screen.queryByText('SKU: 6534606')).not.toBeInTheDocument();
  });

  it('supports cross-category search in both main SearchBar autocomplete and "+ Add Product to Compare" picker after comparing Laptops', async () => {
    vi.mocked(compareProducts).mockResolvedValue(mockComparisonResponse);

    renderWithClient(<App />);

    // 1. Select Laptops category and run a Laptops comparison
    fireEvent.click(screen.getByRole('button', { name: /^laptops$/i }));
    tagTwoDefaultLaptopsAndSubmit('Compare MacBook Air and Dell XPS 13');

    await waitFor(() => {
      expect(screen.getByText('Compared Products')).toBeInTheDocument();
    });

    // Verify Laptops comparison is active and initial 2 Laptop SKUs are tagged
    expect(screen.getByText('SKU: 6534606')).toBeInTheDocument();
    expect(screen.getByText('SKU: 6575132')).toBeInTheDocument();

    // 2. Search for Headphones ("Sony WH-1000XM5") in the main SearchBar autocomplete while Laptops category is active
    const followUpTextarea = screen.getByPlaceholderText(/add follow-up requirements/i);
    fireEvent.change(followUpTextarea, { target: { value: 'Sony WH-1000XM5' } });

    const autocompleteListbox = screen.getByRole('listbox', { name: /product suggestions/i });
    expect(autocompleteListbox).toBeInTheDocument();
    const sonyOption = screen.getByText(/Sony WH-1000XM5 Wireless/i);
    fireEvent.click(sonyOption);

    // Verify Sony WH-1000XM5 (SKU: 6505727) is added to taggedProducts alongside the 2 Laptops
    const taggedRow = screen.getByTestId('tagged-products-row');
    expect(taggedRow).toHaveTextContent('SKU: 6534606');
    expect(taggedRow).toHaveTextContent('SKU: 6575132');
    expect(taggedRow).toHaveTextContent('SKU: 6505727');

    // 3. Open "+ Add Product to Compare" picker and search for another Headphones SKU ("Bose QuietComfort Ultra")
    const addPickerBtn = screen.getByLabelText('Add product to compare');
    fireEvent.click(addPickerBtn);

    const pickerSearchInput = screen.getByPlaceholderText(/search products by name, brand, or sku/i);
    fireEvent.change(pickerSearchInput, { target: { value: 'Bose QuietComfort Ultra' } });

    const boseOption = screen.getByText(/Bose QuietComfort Ultra/i);
    fireEvent.click(boseOption);

    // Verify Bose QuietComfort Ultra (SKU: 6553823) is also added to taggedProducts
    expect(taggedRow).toHaveTextContent('SKU: 6553823');

    // 4. Submit comparison and verify category: null is passed for cross-category tagged products
    fireEvent.submit(screen.getByRole('search'));

    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(2);
    });

    const secondCallArgs = vi.mocked(compareProducts).mock.calls[1][0];
    expect(secondCallArgs.category).toBeNull();
    expect(secondCallArgs.query).toContain('[SKU: 6534606]');
    expect(secondCallArgs.query).toContain('[SKU: 6505727]');
    expect(secondCallArgs.query).toContain('[SKU: 6553823]');
  });
});




