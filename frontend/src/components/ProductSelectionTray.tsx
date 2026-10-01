import React, { useState, useMemo } from 'react';
import { Sparkles, X, Trash2, ArrowRight, Plus, Search } from 'lucide-react';
import { ProductSpec } from '../types/comparison';
import { searchCatalogProducts } from '../data/catalogProducts';

export interface ProductSelectionTrayProps {
  selectedProducts: ProductSpec[];
  onRemoveProduct: (sku: string) => void;
  onClearSelection: () => void;
  onCompare: (products: ProductSpec[]) => void;
  onAddProduct?: (product: ProductSpec) => void;
  maxProducts?: number;
  className?: string;
}

export const ProductSelectionTray: React.FC<ProductSelectionTrayProps> = ({
  selectedProducts,
  onRemoveProduct,
  onClearSelection,
  onCompare,
  onAddProduct,
  maxProducts = 5,
  className = '',
}) => {
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const matches = useMemo(() => {
    const list = searchCatalogProducts(searchQuery);
    return list.filter((p) => !selectedProducts.some((s) => s.sku === p.sku));
  }, [searchQuery, selectedProducts]);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isAddOpen) {
          setIsAddOpen(false);
          setSearchQuery('');
          return;
        }
        if (selectedProducts.length > 0) {
          onClearSelection();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isAddOpen, selectedProducts.length, onClearSelection]);

  if (selectedProducts.length === 0) {
    return null;
  }

  const canCompare = selectedProducts.length >= 2;

  const handleCompareClick = () => {
    if (canCompare) {
      onCompare(selectedProducts);
    }
  };

  return (
    <div
      role="region"
      aria-label="Selected products for comparison"
      className={`fixed bottom-4 left-1/2 -translate-x-1/2 w-11/12 max-w-4xl bg-slate-900/95 backdrop-blur-md text-white rounded-2xl p-4 shadow-2xl border border-blue-500/30 z-40 animate-slideUp transition-all ${className}`}
    >
      {/* Search Popover to Add Products */}
      {isAddOpen && onAddProduct && selectedProducts.length < maxProducts && (
        <div
          role="dialog"
          aria-label="Search and add product to comparison tray"
          className="absolute bottom-full left-0 right-0 mb-3 bg-slate-900/98 border border-slate-700 rounded-2xl p-3 shadow-2xl space-y-2 text-white max-h-72 overflow-hidden flex flex-col z-50 backdrop-blur-md"
        >
          <div className="flex items-center justify-between pb-1 border-b border-slate-800">
            <span className="text-xs font-bold text-gray-200">Add Product to Compare Against</span>
            <button
              type="button"
              onClick={() => {
                setIsAddOpen(false);
                setSearchQuery('');
              }}
              aria-label="Close search popover"
              className="text-gray-400 hover:text-white p-0.5 rounded transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search product to add..."
              aria-label="Search product to add to selection"
              className="w-full bg-slate-800 border border-slate-700 rounded-xl py-2 pl-8 pr-3 text-xs text-white placeholder-gray-400 focus:outline-none focus:border-blue-400"
              autoFocus
            />
          </div>
          <div className="overflow-y-auto custom-scrollbar flex-1 divide-y divide-slate-800">
            {matches.slice(0, 5).map((prod) => (
              <div
                key={prod.sku}
                onClick={() => {
                  onAddProduct(prod);
                  setIsAddOpen(false);
                  setSearchQuery('');
                }}
                className="flex items-center justify-between p-2 hover:bg-slate-800/80 rounded-lg cursor-pointer transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {prod.image_url ? (
                    <img
                      src={prod.image_url}
                      alt=""
                      aria-hidden="true"
                      className="w-6 h-6 object-contain rounded bg-white p-0.5 flex-shrink-0"
                    />
                  ) : null}
                  <div className="min-w-0 text-left">
                    <span className="text-xs font-semibold block truncate max-w-[240px] text-gray-200">
                      {prod.name}
                    </span>
                    <span className="text-[10px] text-gray-400 block">
                      SKU: {prod.sku} • {prod.brand}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                  <span className="text-xs font-bold text-bb-yellow">${prod.price.toFixed(2)}</span>
                  <span className="p-1 rounded bg-bb-yellow text-bb-slate text-[10px] font-bold">
                    + Add
                  </span>
                </div>
              </div>
            ))}
            {matches.length === 0 && (
              <div className="p-3 text-center text-xs text-gray-400">
                No matching products found.
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        {/* Left: Info & items */}
        <div className="flex items-center gap-3 w-full sm:w-auto overflow-hidden">
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="w-7 h-7 rounded-full bg-bb-yellow text-bb-slate font-black text-xs flex items-center justify-center shadow-xs">
              {selectedProducts.length}
            </span>
            <div className="text-left">
              <span className="text-sm font-bold block leading-tight">
                Selected for Comparison
              </span>
              <span className="text-[11px] text-gray-400 block">
                {selectedProducts.length < 2
                  ? 'Select at least 1 more product'
                  : `Ready to compare (${selectedProducts.length}/${maxProducts})`}
              </span>
            </div>
          </div>

          {/* Selected Product Chips List */}
          <div
            className="flex items-center gap-2 overflow-x-auto py-1 px-1 custom-scrollbar max-w-full"
            aria-label="Selected products list"
          >
            {selectedProducts.map((product) => (
              <div
                key={product.sku}
                className="flex items-center gap-1.5 bg-slate-800/90 border border-slate-700 hover:border-slate-500 rounded-lg py-1 px-2.5 flex-shrink-0 text-xs text-gray-200 transition-colors group"
              >
                {product.image_url ? (
                  <img
                    src={product.image_url}
                    alt=""
                    aria-hidden="true"
                    className="w-5 h-5 object-contain rounded bg-white p-0.5"
                  />
                ) : null}
                <span className="max-w-[140px] truncate font-medium" title={product.name}>
                  {product.name}
                </span>
                <button
                  type="button"
                  onClick={() => onRemoveProduct(product.sku)}
                  aria-label={`Remove ${product.name} from selection`}
                  className="text-gray-400 hover:text-red-400 p-0.5 rounded transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2 w-full sm:w-auto justify-end flex-shrink-0">
          {onAddProduct && selectedProducts.length < maxProducts && (
            <button
              type="button"
              onClick={() => setIsAddOpen((prev) => !prev)}
              aria-label="Add product to selection"
              className="inline-flex items-center gap-1.5 text-xs text-blue-200 hover:text-white px-2.5 py-2 rounded-lg bg-blue-900/50 hover:bg-blue-800/70 border border-blue-400/30 transition-colors"
            >
              <Plus className="w-3.5 h-3.5 text-blue-300" />
              <span>Add Product</span>
            </button>
          )}

          <button
            type="button"
            onClick={onClearSelection}
            aria-label="Clear all selected products"
            className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-white px-2.5 py-2 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Clear</span>
          </button>

          <button
            type="button"
            onClick={handleCompareClick}
            disabled={!canCompare}
            aria-label={`Compare ${selectedProducts.length} selected products`}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-bb-yellow text-bb-slate font-extrabold text-xs sm:text-sm rounded-xl hover:bg-bb-yellow-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-md flex-1 sm:flex-initial"
          >
            <Sparkles className="w-4 h-4 text-bb-slate" aria-hidden="true" />
            <span>Compare Selected ({selectedProducts.length})</span>
            <ArrowRight className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
};
