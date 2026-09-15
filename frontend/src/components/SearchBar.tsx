import React, { useState } from 'react';
import { Search, Loader2, X, Laptop, Tablet, Headphones, Home, Tv, Layers } from 'lucide-react';

export interface SearchBarProps {
  onSearch: (query: string, category: string | null) => void;
  isLoading: boolean;
  initialQuery?: string;
  initialCategory?: string | null;
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
  isLoading,
  initialQuery = '',
  initialCategory = null,
  className = '',
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(initialCategory);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed && !isLoading) {
      onSearch(trimmed, selectedCategory);
    }
  };

  const handleClear = () => {
    setQuery('');
  };

  return (
    <div className={`w-full max-w-4xl mx-auto space-y-3 ${className}`}>
      {/* Search Input Box */}
      <form
        onSubmit={handleSubmit}
        role="search"
        className="relative flex items-center shadow-lg rounded-2xl bg-white border-2 border-bb-blue focus-within:ring-4 focus-within:ring-blue-100 transition-all overflow-hidden"
      >
        <div className="pl-5 text-bb-blue flex-shrink-0">
          <Search className="w-6 h-6" aria-hidden="true" />
        </div>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={isLoading}
          placeholder="Compare MacBook Air M3 and Dell XPS 13, or Sony WH-1000XM5 vs Bose QC Ultra..."
          aria-label="Natural language product comparison query"
          className="w-full py-4 px-4 text-base md:text-lg text-gray-900 placeholder-gray-400 bg-transparent focus:outline-none disabled:opacity-50"
        />

        {query && !isLoading && (
          <button
            type="button"
            onClick={handleClear}
            aria-label="Clear search input"
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors mr-1"
          >
            <X className="w-5 h-5" />
          </button>
        )}

        <button
          type="submit"
          disabled={isLoading || !query.trim()}
          className="m-2 px-6 py-3 bg-bb-yellow text-bb-slate font-extrabold text-sm md:text-base rounded-xl hover:bg-bb-yellow-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 shadow-sm flex-shrink-0"
        >
          {isLoading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" />
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
              onClick={() => setSelectedCategory(isSelected && id !== null ? null : id)}
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
