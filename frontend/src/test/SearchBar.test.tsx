import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SearchBar } from '../components/SearchBar';

describe('SearchBar', () => {
  it('renders input with default placeholder and search button', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    expect(screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /compare/i })).toBeInTheDocument();
  });

  it('renders category quick-filter pills', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    expect(screen.getByRole('button', { name: /all categories/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /laptops/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /tablets/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /headphones/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /smart home/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /tvs/i })).toBeInTheDocument();
  });

  it('submits query when search button is clicked', () => {
    const handleSearch = vi.fn();
    render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    const input = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(input, { target: { value: 'Compare iPad Pro vs Galaxy Tab' } });

    const submitBtn = screen.getByRole('button', { name: /compare/i });
    fireEvent.click(submitBtn);

    expect(handleSearch).toHaveBeenCalledTimes(1);
    expect(handleSearch).toHaveBeenCalledWith('Compare iPad Pro vs Galaxy Tab', null);
  });

  it('submits query with selected category filter', () => {
    const handleSearch = vi.fn();
    render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    // Select category pill
    fireEvent.click(screen.getByRole('button', { name: /tablets/i }));

    const input = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(input, { target: { value: 'Compare iPad Pro vs Galaxy Tab' } });

    fireEvent.submit(screen.getByRole('search'));

    expect(handleSearch).toHaveBeenCalledWith('Compare iPad Pro vs Galaxy Tab', 'Tablets');
  });

  it('disables submit button and input when isLoading is true', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={true} />);

    const input = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    const submitBtn = screen.getByRole('button', { name: /comparing/i });

    expect(input).toBeDisabled();
    expect(submitBtn).toBeDisabled();
  });

  it('calls onCategorySelect with category id when a category pill is clicked and null when All Categories is clicked', () => {
    const handleCategorySelect = vi.fn();
    render(
      <SearchBar
        onSearch={vi.fn()}
        onCategorySelect={handleCategorySelect}
        isLoading={false}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /laptops/i }));
    expect(handleCategorySelect).toHaveBeenCalledWith('Laptops');

    fireEvent.click(screen.getByRole('button', { name: /all categories/i }));
    expect(handleCategorySelect).toHaveBeenCalledWith(null);
  });

  it('resets input and selected category when initialQuery and initialCategory props change', () => {
    const { rerender } = render(
      <SearchBar
        onSearch={vi.fn()}
        isLoading={false}
        initialQuery="Compare laptops"
        initialCategory="Laptops"
      />
    );

    const input = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i) as HTMLInputElement;
    expect(input.value).toBe('Compare laptops');
    expect(screen.getByRole('button', { name: /laptops/i })).toHaveAttribute('aria-pressed', 'true');

    rerender(
      <SearchBar
        onSearch={vi.fn()}
        isLoading={false}
        initialQuery=""
        initialCategory={null}
      />
    );

    expect(input.value).toBe('');
    expect(screen.getByRole('button', { name: /all categories/i })).toHaveAttribute('aria-pressed', 'true');
  });

  it('renders tagged SKU chips inside SearchBar when taggedProducts is provided', () => {
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air M3',
        brand: 'Apple',
        price: 1099,
        specifications: { processor: 'Apple M3' },
        in_stock: true,
      },
      {
        sku: '6575132',
        name: 'Dell XPS 13',
        brand: 'Dell',
        price: 1199,
        specifications: { processor: 'Intel Core Ultra 7' },
        in_stock: true,
      },
    ];

    render(
      <SearchBar
        onSearch={vi.fn()}
        isLoading={false}
        taggedProducts={mockProducts}
      />
    );

    expect(screen.getByText(/6534606/)).toBeInTheDocument();
    expect(screen.getByText(/Apple MacBook Air M3/)).toBeInTheDocument();
    expect(screen.getByText(/6575132/)).toBeInTheDocument();
    expect(screen.getByText(/Dell XPS 13/)).toBeInTheDocument();
  });

  it('calls onRemoveTag when the remove button on a tagged SKU chip is clicked', () => {
    const handleRemoveTag = vi.fn();
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air M3',
        brand: 'Apple',
        price: 1099,
        specifications: {},
        in_stock: true,
      },
    ];

    render(
      <SearchBar
        onSearch={vi.fn()}
        isLoading={false}
        taggedProducts={mockProducts}
        onRemoveTag={handleRemoveTag}
      />
    );

    const removeBtn = screen.getByRole('button', {
      name: /remove tag for apple macbook air m3/i,
    });
    fireEvent.click(removeBtn);

    expect(handleRemoveTag).toHaveBeenCalledTimes(1);
    expect(handleRemoveTag).toHaveBeenCalledWith('6534606');
  });

  it('implicitly builds rich comparison prompt with tagged SKUs and user follow-up prompt on submit', () => {
    const handleSearch = vi.fn();
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air M3',
        brand: 'Apple',
        price: 1099,
        specifications: { processor: 'Apple M3' },
        in_stock: true,
      },
      {
        sku: '6575132',
        name: 'Dell XPS 13',
        brand: 'Dell',
        price: 1199,
        specifications: { processor: 'Intel Core Ultra 7' },
        in_stock: true,
      },
    ];

    render(
      <SearchBar
        onSearch={handleSearch}
        isLoading={false}
        taggedProducts={mockProducts}
      />
    );

    // Type a follow-up prompt e.g. "only price"
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'only price' } });

    // Submit form
    fireEvent.submit(screen.getByRole('search'));

    expect(handleSearch).toHaveBeenCalledTimes(1);
    const [submittedQuery, submittedCategory, submittedTagged] = handleSearch.mock.calls[0];

    expect(submittedQuery).toContain('[SKU: 6534606]');
    expect(submittedQuery).toContain('Apple MacBook Air M3');
    expect(submittedQuery).toContain('[SKU: 6575132]');
    expect(submittedQuery).toContain('Dell XPS 13');
    expect(submittedQuery).toContain('User Focus / Follow-up: only price');
    expect(submittedCategory).toBeNull();
    expect(submittedTagged).toEqual(mockProducts);
  });

  it('submits built comparison prompt with default follow-up instruction when user enters no follow-up text', () => {
    const handleSearch = vi.fn();
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air M3',
        brand: 'Apple',
        price: 1099,
        specifications: { processor: 'Apple M3' },
        in_stock: true,
      },
      {
        sku: '6575132',
        name: 'Dell XPS 13',
        brand: 'Dell',
        price: 1199,
        specifications: { processor: 'Intel Core Ultra 7' },
        in_stock: true,
      },
    ];

    render(
      <SearchBar
        onSearch={handleSearch}
        isLoading={false}
        taggedProducts={mockProducts}
      />
    );

    const submitBtn = screen.getByRole('button', { name: /compare/i });
    expect(submitBtn).not.toBeDisabled();
    fireEvent.click(submitBtn);

    expect(handleSearch).toHaveBeenCalledTimes(1);
    const [submittedQuery] = handleSearch.mock.calls[0];
    expect(submittedQuery).toContain('[SKU: 6534606]');
    expect(submittedQuery).toContain('Compare specifications, trade-offs, and recommend the best option.');
  });

  it('removes the last tagged SKU when Backspace is pressed in an empty input', () => {
    const handleRemoveTag = vi.fn();
    const mockProducts = [
      {
        sku: '6534606',
        name: 'MacBook Air',
        brand: 'Apple',
        price: 1099,
        specifications: {},
        in_stock: true,
      },
      {
        sku: '6575132',
        name: 'Dell XPS',
        brand: 'Dell',
        price: 1199,
        specifications: {},
        in_stock: true,
      },
    ];

    render(
      <SearchBar
        onSearch={vi.fn()}
        isLoading={false}
        taggedProducts={mockProducts}
        onRemoveTag={handleRemoveTag}
      />
    );

    const input = screen.getByRole('textbox');
    // Input is empty, press Backspace
    fireEvent.keyDown(input, { key: 'Backspace' });

    expect(handleRemoveTag).toHaveBeenCalledTimes(1);
    expect(handleRemoveTag).toHaveBeenCalledWith('6575132');
  });

  it('calls onClearTags when clear search button is clicked with tagged products present', () => {
    const handleClearTags = vi.fn();
    const mockProducts = [
      {
        sku: '6534606',
        name: 'MacBook Air',
        brand: 'Apple',
        price: 1099,
        specifications: {},
        in_stock: true,
      },
    ];

    render(
      <SearchBar
        onSearch={vi.fn()}
        isLoading={false}
        taggedProducts={mockProducts}
        onClearTags={handleClearTags}
      />
    );

    const clearBtn = screen.getByRole('button', { name: /clear search input/i });
    fireEvent.click(clearBtn);

    expect(handleClearTags).toHaveBeenCalledTimes(1);
  });

  it('widens the container with max-w-5xl for spacious layout', () => {
    const { container } = render(<SearchBar onSearch={vi.fn()} isLoading={false} />);
    const outerContainer = container.firstChild as HTMLElement;
    expect(outerContainer).toHaveClass('max-w-5xl');
  });

  it('renders tagged SKU chips in their own dedicated row above the text input area inside the search container', () => {
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air M3',
        brand: 'Apple',
        price: 1099,
        specifications: {},
        in_stock: true,
      },
    ];

    render(
      <SearchBar
        onSearch={vi.fn()}
        isLoading={false}
        taggedProducts={mockProducts}
      />
    );

    const dedicatedRow = screen.getByTestId('tagged-products-row');
    expect(dedicatedRow).toBeInTheDocument();
    expect(dedicatedRow).toHaveTextContent('SKU: 6534606');
    expect(dedicatedRow).toHaveTextContent('Apple MacBook Air M3');

    // The textarea should be in a separate element below the dedicated row
    const textarea = screen.getByRole('textbox');
    expect(dedicatedRow).not.toContainElement(textarea);
  });

  it('renders a textarea with rows=1 and role=textbox that auto-expands on input', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    const textarea = screen.getByRole('textbox');
    expect(textarea.tagName).toBe('TEXTAREA');
    expect(textarea).toHaveAttribute('rows', '1');
    expect(textarea).toHaveClass('max-h-48');
    expect(textarea).toHaveClass('overflow-y-auto');

    // Simulate input and verify height adjustment
    fireEvent.change(textarea, { target: { value: 'Compare MacBook Air vs Pro with detailed specs\nand battery comparison\nand pricing' } });
    expect((textarea as HTMLTextAreaElement).value).toContain('\n');
  });

  it('submits search when Enter key without Shift is pressed', () => {
    const handleSearch = vi.fn();
    render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Compare iPhone vs Pixel' } });

    const event = fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter', shiftKey: false });
    // Default newline insertion should be prevented
    expect(event).toBe(false);
    expect(handleSearch).toHaveBeenCalledTimes(1);
    expect(handleSearch).toHaveBeenCalledWith('Compare iPhone vs Pixel', null);
  });

  it('does not submit when Enter key is pressed if input is empty and no tagged products', () => {
    const handleSearch = vi.fn();
    render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    const textarea = screen.getByRole('textbox');
    const event = fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter', shiftKey: false });

    // Should prevent default newline but not trigger search
    expect(event).toBe(false);
    expect(handleSearch).not.toHaveBeenCalled();
  });

  it('allows newline and does not submit search when Shift+Enter is pressed', () => {
    const handleSearch = vi.fn();
    render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Compare iPhone' } });

    const event = fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter', shiftKey: true });
    // Should NOT prevent default (allowing newline) and should NOT submit
    expect(event).toBe(true);
    expect(handleSearch).not.toHaveBeenCalled();
  });

  it('resets textarea height when search input is cleared', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} initialQuery="Initial query" />);

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea.value).toBe('Initial query');

    const clearBtn = screen.getByRole('button', { name: /clear search input/i });
    fireEvent.click(clearBtn);

    expect(textarea.value).toBe('');
    expect(textarea.style.height).toBe('auto');
  });

  it('dynamically resizes height up to max 192px as content overflows', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

    // Mock scrollHeight to 120px
    Object.defineProperty(textarea, 'scrollHeight', {
      configurable: true,
      value: 120,
    });

    fireEvent.change(textarea, { target: { value: 'Multiline\nquery\ntext' } });
    expect(textarea.style.height).toBe('120px');

    // Mock scrollHeight exceeding max-h-48 (192px)
    Object.defineProperty(textarea, 'scrollHeight', {
      configurable: true,
      value: 250,
    });

    fireEvent.change(textarea, {
      target: { value: 'Even longer\nmultiline\nquery\ntext\nwith\nmany\nlines' },
    });
    expect(textarea.style.height).toBe('192px');
  });
});


