import React, { useState } from 'react';
import { Star, Package, Check, X } from 'lucide-react';
import { ProductSpec } from '../types/comparison';
import { CitationChip } from './CitationChip';

export interface ProductCardProps {
  product: ProductSpec;
  className?: string;
}

export const ProductCard: React.FC<ProductCardProps> = ({
  product,
  className = '',
}) => {
  const [imageError, setImageError] = useState(false);

  const formattedPrice = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(product.price);

  return (
    <div
      className={`bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col p-4 transition-all hover:shadow-md ${className}`}
    >
      {/* Product Image Area */}
      <div className="relative w-full h-44 bg-gray-100 rounded-lg flex items-center justify-center overflow-hidden mb-3">
        {product.image_url && !imageError ? (
          <img
            src={product.image_url}
            alt={product.name}
            onError={() => setImageError(true)}
            className="w-full h-full object-contain p-2 transition-transform hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-gray-400">
            <Package className="w-12 h-12 stroke-[1.5]" aria-hidden="true" />
            <span className="text-xs mt-1 font-medium">Best Buy Catalog</span>
          </div>
        )}

        {/* Stock Status Badge */}
        <div className="absolute top-2 left-2">
          {product.in_stock ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200 shadow-xs">
              <Check className="w-3 h-3 text-emerald-600" aria-hidden="true" />
              In Stock
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-800 border border-red-200 shadow-xs">
              <X className="w-3 h-3 text-red-600" aria-hidden="true" />
              Out of Stock
            </span>
          )}
        </div>
      </div>

      {/* Brand & Title */}
      <div className="flex-1 flex flex-col">
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="text-xs font-bold uppercase tracking-wider text-bb-blue">
            {product.brand}
          </span>
          <CitationChip sku={product.sku} url={product.url} />
        </div>

        <h3
          className="text-sm font-semibold text-gray-900 line-clamp-2 leading-snug mb-2 hover:text-bb-blue transition-colors"
          title={product.name}
        >
          {product.name}
        </h3>

        {/* Rating & Reviews */}
        {product.rating !== null && product.rating !== undefined && (
          <div className="flex items-center gap-1 text-xs text-gray-600 mb-3">
            <div className="flex items-center text-amber-500">
              <Star className="w-3.5 h-3.5 fill-current" aria-hidden="true" />
            </div>
            <span className="font-semibold text-gray-800">{product.rating.toFixed(1)}</span>
            {product.review_count !== null && product.review_count !== undefined && (
              <span className="text-gray-500">
                ({product.review_count.toLocaleString()} reviews)
              </span>
            )}
          </div>
        )}

        {/* Price & Action */}
        <div className="mt-auto pt-3 border-t border-gray-100 flex items-baseline justify-between">
          <div>
            <span className="text-xs text-gray-500 block">Price</span>
            <span className="text-xl font-black text-gray-900 tracking-tight">
              {formattedPrice}
            </span>
          </div>
          <a
            href={product.url || `https://www.bestbuy.com/site/sku/${product.sku}.p`}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 bg-bb-yellow text-bb-slate font-bold text-xs rounded hover:bg-bb-yellow-hover transition-colors shadow-xs"
          >
            View at Best Buy
          </a>
        </div>
      </div>
    </div>
  );
};
