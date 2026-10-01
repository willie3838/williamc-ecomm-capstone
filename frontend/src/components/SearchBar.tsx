import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Search,
  Loader2,
  X,
  Laptop,
  Tablet,
  Headphones,
  Home,
  Tv,
  Layers,
  Tag,
  Plus,
} from 'lucide-react';
import { ProductSpec } from '../types/comparison';
import { buildComparisonPrompt } from '../utils/promptBuilder';
import { searchCatalogProducts } from '../data/catalogProducts';

export interface SearchBarProps {
  onSearch: (
    query: string,
    category: string | null,
    taggedProducts?: ProductSpec[]
  ) => void;
  onCategorySelect?: (category: string | null) => void;
  isLoading: boolean;
  initialQuery?: string;
  initialCategory?: string | null;
  taggedProducts?: ProductSpec[];
  onAddTag?: (product: ProductSpec) => void;
  onRemoveTag?: (sku: string) => void;
  onClearTags?: () => void;
  maxTaggedProducts?: number;
  className?: string;
}

const CATEGORIES = [
  { id: null, label: 'All Categories', icon: Layers },
  { id: 'Laptops', label: 'Laptops', icon: Laptop },
  { id: 'Tablets', label: 'Tablets', icon: Tablet },
  { id: 'Headphones', label: 'Headphones', icon: Headphones },
  { id: 'Smart Home', label: 'Smart Home', icon: Home },
  { id: 'TVs', label: 'TVs', icon: Tv },
] as const;

export const SearchBar: React.FC<SearchBarProps> = ({
  onSearch,
  onCategorySelect,
  isLoading,
  initialQuery = '',
  initialCategory = null,
  taggedProducts = [],
  onAddTag,
  onRemoveTag,
  onClearTags,
  maxTaggedProducts = 5,
  className = '',
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [prevInitialQuery, setPrevInitialQuery] = useState(initialQuery);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(initialCategory);
  const [prevInitialCategory, setPrevInitialCategory] = useState<string | null>(initialCategory);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState('');
  const [pickerHighlightedIndex, setPickerHighlightedIndex] = useState(-1);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const pickerInputRef = useRef<HTMLInputElement>(null);

  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    if (textarea.value && textarea.scrollHeight > 0) {
      textarea.style.height = `${Math.min(textarea.scrollHeight, 192)}px`;
    }
  };

  useEffect(() => {
    adjustTextareaHeight();
  }, [query]);

  useEffect(() => {
    if (isPickerOpen && pickerInputRef.current) {
      pickerInputRef.current.focus();
    }
  }, [isPickerOpen]);

  if (initialQuery !== prevInitialQuery) {
    setPrevInitialQuery(initialQuery);
    setQuery(initialQuery);
  }

  if (initialCategory !== prevInitialCategory) {
    setPrevInitialCategory(initialCategory);
    setSelectedCategory(initialCategory);
  }

  const hasTaggedProducts = taggedProducts && taggedProducts.length > 0;

  // Filter catalog products by query and selected category, excluding already tagged products
  const availableMatches = useMemo(() => {
    const trimmed = query.trim();
    if (!trimmed) return [];
    const matches = searchCatalogProducts(trimmed, selectedCategory);
    return matches.filter((p) => !taggedProducts.some((t) => t.sku === p.sku));
  }, [query, selectedCategory, taggedProducts]);

  // Catalog picker matches (shows initial suggestions if pickerQuery is empty)
  const pickerMatches = useMemo(() => {
    const trimmed = pickerQuery.trim();
    const matches = searchCatalogProducts(trimmed, selectedCategory);
    return matches.filter((p) => !taggedProducts.some((t) => t.sku === p.sku));
  }, [pickerQuery, selectedCategory, taggedProducts]);

  // Click outside listener to dismiss autocomplete dropdown and picker dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsDropdownOpen(false);
        setHighlightedIndex(-1);
        setIsPickerOpen(false);
        setPickerHighlightedIndex(-1);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectProduct = (product: ProductSpec) => {
    if (taggedProducts.length >= maxTaggedProducts) return;
    if (onAddTag) {
      onAddTag(product);
    }
    setQuery('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    setIsDropdownOpen(false);
    setHighlightedIndex(-1);
  };

  const handleSelectPickerProduct = (product: ProductSpec) => {
    handleSelectProduct(product);
    setIsPickerOpen(false);
    setPickerQuery('');
    setPickerHighlightedIndex(-1);
  };

  const canSubmit = !isLoading && (query.trim().length > 0 || hasTaggedProducts);

  const executeSearch = () => {
    setIsDropdownOpen(false);
    setHighlightedIndex(-1);
    const trimmed = query.trim();

    if (hasTaggedProducts) {
      if (!isLoading) {
        const prompt = buildComparisonPrompt(taggedProducts, trimmed);
        onSearch(prompt, selectedCategory, taggedProducts);
      }
      return;
    }

    if (trimmed && !isLoading) {
      onSearch(trimmed, selectedCategory);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeSearch();
  };

  const handleClear = () => {
    setQuery('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    setIsDropdownOpen(false);
    setHighlightedIndex(-1);
    if (hasTaggedProducts && onClearTags) {
      onClearTags();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setIsDropdownOpen(true);
      if (availableMatches.length > 0) {
        setHighlightedIndex((prev) => (prev + 1) % availableMatches.length);
      }
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setIsDropdownOpen(true);
      if (availableMatches.length > 0) {
        setHighlightedIndex((prev) =>
          prev <= 0 ? availableMatches.length - 1 : prev - 1
        );
      }
      return;
    }

    if (e.key === 'Enter') {
      if (!e.shiftKey) {
        e.preventDefault();
        if (isDropdownOpen && highlightedIndex >= 0 && availableMatches[highlightedIndex]) {
          e.stopPropagation();
          handleSelectProduct(availableMatches[highlightedIndex]);
          return;
        }
        if (canSubmit) {
          executeSearch();
        }
        return;
      }
      return;
    }

    if (e.key === 'Escape') {
      if (isDropdownOpen) {
        e.preventDefault();
        setIsDropdownOpen(false);
        setHighlightedIndex(-1);
        return;
      }
    }

    if (e.key === 'Backspace' && query === '' && hasTaggedProducts && onRemoveTag) {
      const lastProduct = taggedProducts[taggedProducts.length - 1];
      onRemoveTag(lastProduct.sku);
    }
  };

  const handleCategoryClick = (id: string | null) => {
    setSelectedCategory(id);
    onCategorySelect?.(id);
  };

  return (
    <div className={`w-full max-w-5xl mx-auto space-y-3 ${className}`}>
      {/* Combobox wrapper */}
      <div
        ref={containerRef}
        role="combobox"
        aria-expanded={(isDropdownOpen && availableMatches.length > 0) || isPickerOpen}
        aria-haspopup="listbox"
        aria-controls={isPickerOpen ? 'catalog-product-picker-listbox' : 'product-search-listbox'}
        className="relative"
      >
        {/* Search Input Box */}
        <form
          onSubmit={handleSubmit}
          role="search"
          className="relative flex flex-col shadow-lg rounded-2xl bg-white border-2 border-bb-blue focus-within:ring-4 focus-within:ring-blue-100 transition-all p-2 sm:p-2.5"
        >
          {/* Tagged SKU Chips Dedicated Row */}
          {hasTaggedProducts && (
            <div
              data-testid="tagged-products-row"
              className="flex flex-wrap items-center gap-1.5 px-2.5 pt-1 pb-2 border-b border-gray-100 w-full"
            >
              {taggedProducts.map((prod) => (
                <span
                  key={prod.sku}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-blue-50 text-bb-blue border border-blue-200 shadow-2xs group"
                >
                  <Tag className="w-3 h-3 text-bb-blue/70" aria-hidden="true" />
                  <span className="font-mono text-[11px] text-blue-600 font-bold">
                    SKU: {prod.sku}
                  </span>
                  <span className="max-w-[140px] sm:max-w-[200px] truncate font-medium text-gray-800">
                    {prod.name}
                  </span>
                  {onRemoveTag && !isLoading && (
                    <button
                      type="button"
                      onClick={() => onRemoveTag(prod.sku)}
                      aria-label={`Remove tag for ${prod.name}`}
                      className="p-0.5 rounded-full hover:bg-blue-200/60 text-gray-400 hover:text-gray-700 transition-colors ml-0.5"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}

          {/* Always-visible '+ Add Product to Compare' search trigger button/bar (when < maxTaggedProducts) */}
          {taggedProducts.length < maxTaggedProducts && (
            <div className="flex items-center justify-between px-2.5 pt-1 pb-1.5 border-b border-gray-100/80">
              <button
                type="button"
                onClick={() => {
                  setIsPickerOpen((prev) => !prev);
                  setIsDropdownOpen(false);
                }}
                aria-label="Add product to compare"
                aria-expanded={isPickerOpen}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold text-bb-blue bg-blue-50/80 hover:bg-blue-100 hover:text-blue-900 border border-blue-200 transition-colors cursor-pointer shadow-2xs"
              >
                <Plus className="w-3.5 h-3.5 md:w-4 md:h-4 text-bb-blue" aria-hidden="true" />
                <span>+ Add Product to Compare</span>
              </button>
              <span className="text-[11px] text-gray-500 font-medium hidden sm:inline">
                {taggedProducts.length === 0
                  ? 'Browse catalog & pick products to compare'
                  : `${taggedProducts.length} of ${maxTaggedProducts} tagged`}
              </span>
            </div>
          )}

          {/* Text Input Row */}
          <div className="flex items-center gap-2 w-full pt-1">
            <div className="pl-2 pr-1 text-bb-blue flex-shrink-0 flex items-center self-center">
              <Search className="w-5 h-5 md:w-6 md:h-6" aria-hidden="true" />
            </div>

            <textarea
              ref={textareaRef}
              rows={1}
              role="textbox"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setIsDropdownOpen(true);
                setIsPickerOpen(false);
                setHighlightedIndex(-1);
              }}
              onFocus={() => {
                if (query.trim() && availableMatches.length > 0) {
                  setIsDropdownOpen(true);
                  setIsPickerOpen(false);
                }
              }}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              placeholder={
                hasTaggedProducts
                  ? 'Add follow-up requirements (e.g., "only price", "good for gaming", "battery life")...'
                  : 'Compare MacBook Air M3 and Dell XPS 13, or Sony WH-1000XM5 vs Bose QC Ultra...'
              }
              aria-label="Natural language product comparison query"
              aria-autocomplete="list"
              aria-activedescendant={
                highlightedIndex >= 0 && availableMatches[highlightedIndex]
                  ? `product-opt-${availableMatches[highlightedIndex].sku}`
                  : undefined
              }
              className="flex-1 min-w-0 resize-none py-2 px-2 text-sm md:text-base text-gray-900 placeholder-gray-400 bg-transparent focus:outline-none disabled:opacity-50 max-h-48 overflow-y-auto leading-relaxed custom-scrollbar"
            />

            {(query || hasTaggedProducts) && !isLoading && (
              <button
                type="button"
                onClick={handleClear}
                aria-label="Clear search input"
                className="p-2 text-gray-400 hover:text-gray-600 transition-colors mr-0.5 flex-shrink-0 self-center"
              >
                <X className="w-5 h-5" />
              </button>
            )}

            <button
              type="submit"
              disabled={!canSubmit}
              className="px-5 py-2.5 bg-bb-yellow text-bb-slate font-extrabold text-sm md:text-base rounded-xl hover:bg-bb-yellow-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 shadow-xs flex-shrink-0 self-center"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 md:w-5 md:h-5 animate-spin" aria-hidden="true" />
                  <span>Comparing...</span>
                </>
              ) : (
                <span>Compare</span>
              )}
            </button>
          </div>
        </form>

        {/* Catalog Product Picker Dropdown Listbox */}
        {isPickerOpen && (
          <div
            id="catalog-product-picker-listbox"
            role="listbox"
            aria-label="Catalog product picker"
            className="absolute top-full left-0 right-0 mt-2 bg-white rounded-2xl shadow-2xl border border-gray-200 divide-y divide-gray-100 max-h-96 overflow-hidden z-50 flex flex-col"
          >
            {/* Inline Search Input in Dropdown Header */}
            <div className="p-3 bg-gray-50 border-b border-gray-200 flex items-center gap-2">
              <Search className="w-4 h-4 text-gray-400 flex-shrink-0" aria-hidden="true" />
              <input
                ref={pickerInputRef}
                type="text"
                value={pickerQuery}
                onChange={(e) => {
                  setPickerQuery(e.target.value);
                  setPickerHighlightedIndex(-1);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    setIsPickerOpen(false);
                  } else if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (pickerMatches.length > 0) {
                      setPickerHighlightedIndex((prev) => (prev + 1) % pickerMatches.length);
                    }
                  } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (pickerMatches.length > 0) {
                      setPickerHighlightedIndex((prev) => (prev <= 0 ? pickerMatches.length - 1 : prev - 1));
                    }
                  } else if (e.key === 'Enter') {
                    e.preventDefault();
                    if (pickerHighlightedIndex >= 0 && pickerMatches[pickerHighlightedIndex]) {
                      handleSelectPickerProduct(pickerMatches[pickerHighlightedIndex]);
                    }
                  }
                }}
                placeholder="Search products by name, brand, or SKU..."
                aria-label="Search products to compare"
                className="w-full bg-white text-sm text-gray-900 placeholder-gray-400 rounded-lg px-3 py-1.5 border border-gray-300 focus:outline-none focus:ring-2 focus:ring-bb-blue"
              />
              {pickerQuery && (
                <button
                  type="button"
                  onClick={() => setPickerQuery('')}
                  aria-label="Clear picker search"
                  className="p-1 text-gray-400 hover:text-gray-600"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Suggestions list */}
            <div className="overflow-y-auto max-h-72 divide-y divide-gray-100 custom-scrollbar">
              {pickerMatches.length === 0 ? (
                <div className="p-4 text-center text-sm text-gray-500">
                  No catalog products found matching &ldquo;{pickerQuery}&rdquo;.
                </div>
              ) : (
                pickerMatches.slice(0, 8).map((product, idx) => {
                  const isHighlighted = idx === pickerHighlightedIndex;
                  return (
                    <div
                      key={product.sku}
                      id={`picker-opt-${product.sku}`}
                      role="option"
                      data-sku={product.sku}
                      aria-selected={isHighlighted}
                      onClick={() => handleSelectPickerProduct(product)}
                      onMouseEnter={() => setPickerHighlightedIndex(idx)}
                      className={`flex items-center justify-between p-3 cursor-pointer transition-colors ${
                        isHighlighted
                          ? 'bg-blue-50 text-bb-blue'
                          : 'hover:bg-gray-50 text-gray-900'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {product.image_url ? (
                          <img
                            src={product.image_url}
                            alt=""
                            aria-hidden="true"
                            className="w-10 h-10 object-contain rounded bg-white p-1 border border-gray-100 flex-shrink-0"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded bg-gray-100 flex items-center justify-center flex-shrink-0">
                            <Tag className="w-5 h-5 text-gray-400" />
                          </div>
                        )}
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-mono font-bold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200">
                              SKU: {product.sku}
                            </span>
                            <span className="text-xs text-gray-500 font-medium">
                              {product.brand} • {product.category}
                            </span>
                          </div>
                          <div className="font-semibold text-sm truncate max-w-sm sm:max-w-md text-gray-900">
                            {product.name}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 flex-shrink-0 ml-2">
                        <span className="font-bold text-sm text-gray-900">
                          ${product.price.toFixed(2)}
                        </span>
                        <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-lg bg-bb-yellow text-bb-slate shadow-2xs hover:bg-bb-yellow-hover">
                          <Plus className="w-3.5 h-3.5" />
                          <span className="hidden sm:inline">Add to compare</span>
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}

        {/* Autocomplete Dropdown Listbox */}
        {isDropdownOpen && availableMatches.length > 0 && (
          <div
            id="product-search-listbox"
            role="listbox"
            aria-label="Product suggestions"
            className="absolute top-full left-0 right-0 mt-2 bg-white rounded-2xl shadow-2xl border border-gray-200 divide-y divide-gray-100 max-h-80 overflow-y-auto z-50 custom-scrollbar"
          >
            {availableMatches.slice(0, 8).map((product, idx) => {
              const isHighlighted = idx === highlightedIndex;
              const isMaxReached = taggedProducts.length >= maxTaggedProducts;

              return (
                <div
                  key={product.sku}
                  id={`product-opt-${product.sku}`}
                  role="option"
                  data-sku={product.sku}
                  aria-selected={isHighlighted}
                  onClick={() => handleSelectProduct(product)}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                  className={`flex items-center justify-between p-3 cursor-pointer transition-colors ${
                    isHighlighted
                      ? 'bg-blue-50 text-bb-blue'
                      : 'hover:bg-gray-50 text-gray-900'
                  } ${isMaxReached ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {product.image_url ? (
                      <img
                        src={product.image_url}
                        alt=""
                        aria-hidden="true"
                        className="w-10 h-10 object-contain rounded bg-white p-1 border border-gray-100 flex-shrink-0"
                      />
                    ) : (
                      <div className="w-10 h-10 rounded bg-gray-100 flex items-center justify-center flex-shrink-0">
                        <Tag className="w-5 h-5 text-gray-400" />
                      </div>
                    )}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-mono font-bold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200">
                          SKU: {product.sku}
                        </span>
                        <span className="text-xs text-gray-500 font-medium">
                          {product.brand} • {product.category}
                        </span>
                      </div>
                      <div className="font-semibold text-sm truncate max-w-sm sm:max-w-md text-gray-900">
                        {product.name}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0 ml-2">
                    <span className="font-bold text-sm text-gray-900">
                      ${product.price.toFixed(2)}
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-lg bg-bb-yellow text-bb-slate shadow-2xs hover:bg-bb-yellow-hover">
                      <Plus className="w-3.5 h-3.5" />
                      <span className="hidden sm:inline">Add to compare</span>
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Category Pills */}
      <div
        className="flex items-center gap-2 overflow-x-auto pb-1 custom-scrollbar text-xs font-semibold"
        role="group"
        aria-label="Filter by product category"
      >
        <span className="text-gray-500 flex-shrink-0 pl-1">Filter category:</span>
        {CATEGORIES.map(({ id, label, icon: Icon }) => {
          const isSelected = selectedCategory === id;
          return (
            <button
              key={label}
              type="button"
              onClick={() => handleCategoryClick(id)}
              aria-pressed={isSelected}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border transition-all flex-shrink-0 ${
                isSelected
                  ? 'bg-bb-blue text-white border-bb-blue shadow-xs font-bold'
                  : 'bg-white text-gray-700 border-gray-200 hover:border-gray-300 hover:bg-gray-50'
              }`}
            >
              <Icon className="w-3.5 h-3.5" aria-hidden="true" />
              <span>{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
