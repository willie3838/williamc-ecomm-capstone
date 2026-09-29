import React from 'react';
import { Sparkles, X, Trash2, ArrowRight } from 'lucide-react';
import { ProductSpec } from '../types/comparison';

export interface ProductSelectionTrayProps {
  selectedProducts: ProductSpec[];
  onRemoveProduct: (sku: string) => void;
  onClearSelection: () => void;
  onCompare: (products: ProductSpec[]) => void;
  maxProducts?: number;
  className?: string;
}

export const ProductSelectionTray: React.FC<ProductSelectionTrayProps> = ({
  selectedProducts,
  onRemoveProduct,
  onClearSelection,
  onCompare,
  maxProducts = 4,
  className = '',
}) => {
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && selectedProducts.length > 0) {
        onClearSelection();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedProducts.length, onClearSelection]);

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
