import React, { useState } from 'react';
import { Search, Loader2, X, Laptop, Tablet, Headphones, Home, Tv, Layers, Tag } from 'lucide-react';
import { ProductSpec } from '../types/comparison';
import { buildComparisonPrompt } from '../utils/promptBuilder';

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
  onRemoveTag?: (sku: string) => void;
  onClearTags?: () => void;
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
  onRemoveTag,
  onClearTags,
  className = '',
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [prevInitialQuery, setPrevInitialQuery] = useState(initialQuery);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(initialCategory);
  const [prevInitialCategory, setPrevInitialCategory] = useState<string | null>(initialCategory);

  if (initialQuery !== prevInitialQuery) {
    setPrevInitialQuery(initialQuery);
    setQuery(initialQuery);
  }

  if (initialCategory !== prevInitialCategory) {
    setPrevInitialCategory(initialCategory);
    setSelectedCategory(initialCategory);
  }

  const hasTaggedProducts = taggedProducts && taggedProducts.length > 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
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

  const handleClear = () => {
    setQuery('');
    if (hasTaggedProducts && onClearTags) {
      onClearTags();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && query === '' && hasTaggedProducts && onRemoveTag) {
      const lastProduct = taggedProducts[taggedProducts.length - 1];
      onRemoveTag(lastProduct.sku);
    }
  };

  const handleCategoryClick = (id: string | null) => {
    setSelectedCategory(id);
    onCategorySelect?.(id);
  };

  const canSubmit = !isLoading && (query.trim().length > 0 || hasTaggedProducts);

  return (
    <div className={`w-full max-w-4xl mx-auto space-y-3 ${className}`}>
      {/* Search Input Box */}
      <form
        onSubmit={handleSubmit}
        role="search"
        className="relative flex flex-wrap sm:flex-nowrap items-center shadow-lg rounded-2xl bg-white border-2 border-bb-blue focus-within:ring-4 focus-within:ring-blue-100 transition-all overflow-hidden p-1.5"
      >
        <div className="pl-3.5 pr-1 text-bb-blue flex-shrink-0 flex items-center">
          <Search className="w-5 h-5 md:w-6 md:h-6" aria-hidden="true" />
        </div>

        {/* Tagged SKU Chips */}
        {hasTaggedProducts && (
          <div className="flex flex-wrap items-center gap-1.5 px-1 py-1 max-w-full">
            {taggedProducts.map((prod) => (
              <span
                key={prod.sku}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-blue-50 text-bb-blue border border-blue-200 shadow-2xs group"
              >
                <Tag className="w-3 h-3 text-bb-blue/70" aria-hidden="true" />
                <span className="font-mono text-[11px] text-blue-600 font-bold">
                  SKU: {prod.sku}
                </span>
                <span className="max-w-[120px] sm:max-w-[160px] truncate font-medium text-gray-800">
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

        {/* Text Input */}
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          placeholder={
            hasTaggedProducts
              ? 'Add follow-up requirements (e.g., "only price", "good for gaming", "battery life")...'
              : 'Compare MacBook Air M3 and Dell XPS 13, or Sony WH-1000XM5 vs Bose QC Ultra...'
          }
          aria-label="Natural language product comparison query"
          className="flex-1 min-w-[180px] py-2.5 px-3 text-sm md:text-base text-gray-900 placeholder-gray-400 bg-transparent focus:outline-none disabled:opacity-50"
        />

        {(query || hasTaggedProducts) && !isLoading && (
          <button
            type="button"
            onClick={handleClear}
            aria-label="Clear search input"
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors mr-1 flex-shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="m-1 px-5 py-2.5 bg-bb-yellow text-bb-slate font-extrabold text-sm md:text-base rounded-xl hover:bg-bb-yellow-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 shadow-xs flex-shrink-0"
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
      </form>

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
