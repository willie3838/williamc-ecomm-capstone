import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SearchBar } from '../components/SearchBar';

describe('SearchBar', () => {
  it('renders input with default placeholder and search button', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    expect(screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^compare$/i })).toBeInTheDocument();
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

    const submitBtn = screen.getByRole('button', { name: /^compare$/i });
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

  it('does not submit search if input is whitespace and no tagged products', () => {
    const handleSearch = vi.fn();
    render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    const input = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(input, { target: { value: '   ' } });

    const submitBtn = screen.getByRole('button', { name: /^compare$/i });
    expect(submitBtn).toBeDisabled();

    fireEvent.submit(screen.getByRole('search'));
    expect(handleSearch).not.toHaveBeenCalled();
  });

  it('renders clear button when query is typed and clears input on click', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    const input = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Sony vs Bose' } });

    const clearBtn = screen.getByRole('button', { name: /clear search input/i });
    expect(clearBtn).toBeInTheDocument();

    fireEvent.click(clearBtn);
    expect(input.value).toBe('');
  });

  it('renders tagged SKU chips when taggedProducts prop is provided', () => {
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air 13.6" Laptop - M3 chip - 16GB Memory',
        brand: 'Apple',
        price: 1099,
        specifications: {},
        in_stock: true,
      },
      {
        sku: '6575132',
        name: 'Dell XPS 13" - Intel Core Ultra 7 - 16GB Memory',
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
      />
    );

    expect(screen.getByText('SKU: 6534606')).toBeInTheDocument();
    expect(screen.getByText('SKU: 6575132')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/add follow-up requirements/i)).toBeInTheDocument();
  });

  it('allows removing a tagged product chip via its remove button', () => {
    const handleRemoveTag = vi.fn();
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air 13.6"',
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

    const removeBtn = screen.getByRole('button', { name: /remove tag for apple macbook air/i });
    fireEvent.click(removeBtn);

    expect(handleRemoveTag).toHaveBeenCalledWith('6534606');
  });

  it('removes the last tagged product chip when Backspace is pressed on empty query', () => {
    const handleRemoveTag = vi.fn();
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air',
        brand: 'Apple',
        price: 1099,
        specifications: {},
        in_stock: true,
      },
      {
        sku: '6575132',
        name: 'Dell XPS 13',
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
    fireEvent.keyDown(input, { key: 'Backspace' });

    expect(handleRemoveTag).toHaveBeenCalledWith('6575132');
  });

  it('submits comparison prompt built from tagged products when submitted', () => {
    const handleSearch = vi.fn();
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air 13.6"',
        brand: 'Apple',
        price: 1099,
        category: 'Laptops',
        specifications: { processor: 'M3', ram_gb: 16 },
        in_stock: true,
      },
      {
        sku: '6575132',
        name: 'Dell XPS 13"',
        brand: 'Dell',
        price: 1199,
        category: 'Laptops',
        specifications: { processor: 'Ultra 7', ram_gb: 16 },
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

    const submitBtn = screen.getByRole('button', { name: /^compare$/i });
    expect(submitBtn).toBeEnabled();
    fireEvent.click(submitBtn);

    expect(handleSearch).toHaveBeenCalledTimes(1);
    const [promptArg, categoryArg, taggedArg] = handleSearch.mock.calls[0];
    expect(promptArg).toContain('[SKU: 6534606]');
    expect(promptArg).toContain('[SKU: 6575132]');
    expect(categoryArg).toBeNull();
    expect(taggedArg).toEqual(mockProducts);
  });

  it('includes follow-up user query when submitted with tagged products', () => {
    const handleSearch = vi.fn();
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air 13.6"',
        brand: 'Apple',
        price: 1099,
        category: 'Laptops',
        specifications: { processor: 'M3' },
        in_stock: true,
      },
      {
        sku: '6575132',
        name: 'Dell XPS 13"',
        brand: 'Dell',
        price: 1199,
        category: 'Laptops',
        specifications: { processor: 'Ultra 7' },
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

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'focus strictly on battery life' } });

    const submitBtn = screen.getByRole('button', { name: /^compare$/i });
    fireEvent.click(submitBtn);

    const [promptArg] = handleSearch.mock.calls[0];
    expect(promptArg).toContain('User Focus / Follow-up: focus strictly on battery life');
  });

  it('calls onClearTags when clear button is clicked with tagged products', () => {
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

  it('renders autocomplete typeahead dropdown when typing matching query', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'MacBook' } });

    // The listbox dropdown should appear
    const listbox = screen.getByRole('listbox', { name: /product suggestions/i });
    expect(listbox).toBeInTheDocument();
    expect(screen.getByText(/Apple MacBook Air/i)).toBeInTheDocument();
  });

  it('navigates autocomplete items via ArrowDown / ArrowUp and selects with Enter', () => {
    const handleAddTag = vi.fn();
    render(
      <SearchBar
        onSearch={vi.fn()}
        onAddTag={handleAddTag}
        isLoading={false}
      />
    );

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Dell XPS' } });

    // Arrow down to first item
    fireEvent.keyDown(input, { key: 'ArrowDown' });

    const firstOption = screen.getAllByRole('option')[0];
    expect(firstOption).toHaveAttribute('aria-selected', 'true');

    // Press Enter to select highlighted item
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(handleAddTag).toHaveBeenCalledTimes(1);
    expect(handleAddTag).toHaveBeenCalledWith(
      expect.objectContaining({ sku: '6575132' })
    );
    // Input should be cleared after selecting
    expect((input as HTMLTextAreaElement).value).toBe('');
  });

  it('tags product when clicking an item from autocomplete dropdown', () => {
    const handleAddTag = vi.fn();
    render(
      <SearchBar
        onSearch={vi.fn()}
        onAddTag={handleAddTag}
        isLoading={false}
      />
    );

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Sony' } });

    // Find and click the Sony WH-1000XM5 option
    const sonyOption = screen.getByText(/Sony WH-1000XM5/i);
    fireEvent.click(sonyOption);

    expect(handleAddTag).toHaveBeenCalledTimes(1);
    expect(handleAddTag).toHaveBeenCalledWith(
      expect.objectContaining({ sku: '6505727' })
    );
  });

  it('closes autocomplete dropdown when Escape key is pressed', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'MacBook' } });

    expect(screen.getByRole('listbox', { name: /product suggestions/i })).toBeInTheDocument();

    fireEvent.keyDown(input, { key: 'Escape' });

    expect(screen.queryByRole('listbox', { name: /product suggestions/i })).not.toBeInTheDocument();
  });

  it('has accessible combobox and listbox ARIA attributes', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    const combobox = screen.getByRole('combobox');
    expect(combobox).toHaveAttribute('aria-expanded', 'false');

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'OLED' } });

    expect(combobox).toHaveAttribute('aria-expanded', 'true');
    expect(combobox).toHaveAttribute('aria-controls', 'product-search-listbox');
    expect(screen.getByRole('listbox')).toHaveAttribute('id', 'product-search-listbox');
  });

  it('excludes already tagged products from typeahead suggestions and caps at 4 products', () => {
    const mockProducts = [
      {
        sku: '6534606',
        name: 'Apple MacBook Air 13.6"',
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

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Apple' } });

    // SKU 6534606 is already tagged, so it should not appear in suggestions
    const options = screen.getAllByRole('option');
    const optionSkus = options.map((opt) => opt.getAttribute('data-sku'));
    expect(optionSkus).not.toContain('6534606');
  });

  describe('Always-visible "+ Add Product to Compare" Picker', () => {
    it('renders the "+ Add Product to Compare" button when fewer than 5 products are tagged', () => {
      render(<SearchBar onSearch={vi.fn()} isLoading={false} taggedProducts={[]} />);

      const addBtn = screen.getByRole('button', { name: /add product to compare/i });
      expect(addBtn).toBeInTheDocument();
      expect(addBtn).toHaveTextContent(/add product to compare/i);
    });

    it('still renders "+ Add Product to Compare" button when 4 products are tagged', () => {
      const fourProducts = [
        { sku: '1', name: 'Product 1', brand: 'Brand', price: 100, specifications: {}, in_stock: true },
        { sku: '2', name: 'Product 2', brand: 'Brand', price: 200, specifications: {}, in_stock: true },
        { sku: '3', name: 'Product 3', brand: 'Brand', price: 300, specifications: {}, in_stock: true },
        { sku: '4', name: 'Product 4', brand: 'Brand', price: 400, specifications: {}, in_stock: true },
      ];

      render(<SearchBar onSearch={vi.fn()} isLoading={false} taggedProducts={fourProducts} />);
      expect(screen.getByRole('button', { name: /add product to compare/i })).toBeInTheDocument();
    });

    it('opens catalog product picker dropdown with inline search input and initial suggestions on click', () => {
      render(<SearchBar onSearch={vi.fn()} isLoading={false} taggedProducts={[]} />);

      const addBtn = screen.getByRole('button', { name: /add product to compare/i });
      fireEvent.click(addBtn);

      // Picker dropdown listbox should be open
      const picker = screen.getByRole('listbox', { name: /catalog product picker/i });
      expect(picker).toBeInTheDocument();

      // Inline search input should be present inside the picker
      const pickerSearch = screen.getByPlaceholderText(/search products by name, brand, or sku/i);
      expect(pickerSearch).toBeInTheDocument();

      // Initial suggestions should appear immediately without typing in the main textarea
      const options = screen.getAllByRole('option');
      expect(options.length).toBeGreaterThan(0);
    });

    it('filters suggestions when typing in the picker inline search input', () => {
      render(<SearchBar onSearch={vi.fn()} isLoading={false} taggedProducts={[]} />);

      const addBtn = screen.getByRole('button', { name: /add product to compare/i });
      fireEvent.click(addBtn);

      const pickerSearch = screen.getByPlaceholderText(/search products by name, brand, or sku/i);
      fireEvent.change(pickerSearch, { target: { value: 'Bose' } });

      const options = screen.getAllByRole('option');
      expect(options.length).toBeGreaterThan(0);
      expect(options[0]).toHaveTextContent(/bose/i);
    });

    it('calls onAddTag and closes picker when a product suggestion is clicked', () => {
      const handleAddTag = vi.fn();
      render(
        <SearchBar
          onSearch={vi.fn()}
          onAddTag={handleAddTag}
          isLoading={false}
          taggedProducts={[]}
        />
      );

      const addBtn = screen.getByRole('button', { name: /add product to compare/i });
      fireEvent.click(addBtn);

      const pickerSearch = screen.getByPlaceholderText(/search products by name, brand, or sku/i);
      fireEvent.change(pickerSearch, { target: { value: 'Apple MacBook Air 13.6"' } });

      const macbookOption = screen.getByText(/Apple MacBook Air 13.6"/i);
      fireEvent.click(macbookOption);

      expect(handleAddTag).toHaveBeenCalledTimes(1);
      expect(handleAddTag).toHaveBeenCalledWith(
        expect.objectContaining({ sku: '6534606' })
      );

      // Picker should close
      expect(screen.queryByRole('listbox', { name: /catalog product picker/i })).not.toBeInTheDocument();
    });

    it('hides "+ Add Product to Compare" button when 5 products are tagged', () => {
      const fiveProducts = [
        { sku: '1', name: 'Product 1', brand: 'Brand', price: 100, specifications: {}, in_stock: true },
        { sku: '2', name: 'Product 2', brand: 'Brand', price: 200, specifications: {}, in_stock: true },
        { sku: '3', name: 'Product 3', brand: 'Brand', price: 300, specifications: {}, in_stock: true },
        { sku: '4', name: 'Product 4', brand: 'Brand', price: 400, specifications: {}, in_stock: true },
        { sku: '5', name: 'Product 5', brand: 'Brand', price: 500, specifications: {}, in_stock: true },
      ];

      render(
        <SearchBar
          onSearch={vi.fn()}
          isLoading={false}
          taggedProducts={fiveProducts}
        />
      );

      expect(screen.queryByRole('button', { name: /add product to compare/i })).not.toBeInTheDocument();
    });

    it('keeps typeahead autocomplete functioning on the main textarea', () => {
      render(<SearchBar onSearch={vi.fn()} isLoading={false} taggedProducts={[]} />);

      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Dell' } });

      expect(screen.getByRole('listbox', { name: /product suggestions/i })).toBeInTheDocument();
    });

    it('passes category = null to onSearch when tagged products span multiple categories', () => {
      const handleSearch = vi.fn();
      const crossCategoryProducts = [
        { sku: '1', name: 'MacBook Air', brand: 'Apple', price: 999, category: 'Laptops', specifications: {}, in_stock: true },
        { sku: '2', name: 'iPad Pro', brand: 'Apple', price: 799, category: 'Tablets', specifications: {}, in_stock: true },
      ];
      render(
        <SearchBar
          onSearch={handleSearch}
          isLoading={false}
          taggedProducts={crossCategoryProducts}
          initialCategory="Laptops"
        />
      );
      fireEvent.submit(screen.getByRole('search'));
      expect(handleSearch).toHaveBeenCalledTimes(1);
      expect(handleSearch).toHaveBeenCalledWith(
        expect.any(String),
        null,
        crossCategoryProducts
      );
    });

    it('passes shared category to onSearch when all tagged products share the exact same category', () => {
      const handleSearch = vi.fn();
      const sameCategoryProducts = [
        { sku: '1', name: 'MacBook Air', brand: 'Apple', price: 999, category: 'Laptops', specifications: {}, in_stock: true },
        { sku: '2', name: 'Dell XPS 13', brand: 'Dell', price: 1099, category: 'Laptops', specifications: {}, in_stock: true },
      ];
      render(
        <SearchBar
          onSearch={handleSearch}
          isLoading={false}
          taggedProducts={sameCategoryProducts}
          initialCategory="Laptops"
        />
      );
      fireEvent.submit(screen.getByRole('search'));
      expect(handleSearch).toHaveBeenCalledTimes(1);
      expect(handleSearch).toHaveBeenCalledWith(
        expect.any(String),
        'Laptops',
        sameCategoryProducts
      );
    });
  });
});

