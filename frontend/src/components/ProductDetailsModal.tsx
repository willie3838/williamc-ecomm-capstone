import React, { useEffect, useState } from 'react';
import {
  X,
  Star,
  Package,
  Check,
  ShieldCheck,
  ExternalLink,
  Plus,
  CheckCheck,
} from 'lucide-react';
import { ProductSpec } from '../types/comparison';

export interface ProductDetailsModalProps {
  product: ProductSpec | null;
  isOpen: boolean;
  onClose: () => void;
  onSelectForCompare?: (product: ProductSpec) => void;
  isSelectedForCompare?: boolean;
}

/**
 * Format specification keys nicely (e.g. 'ram_gb' -> 'RAM (GB)', 'battery_life_hours' -> 'Battery Life (Hours)').
 */
const formatSpecKey = (key: string): string => {
  const customLabels: Record<string, string> = {
    processor: 'Processor',
    ram_gb: 'RAM Memory',
    storage_gb: 'Storage',
    battery_life_hours: 'Battery Life',
    weight_lbs: 'Weight',
    weight_oz: 'Weight',
    display_size_in: 'Screen Size',
    display_resolution: 'Display Resolution',
    refresh_rate_hz: 'Refresh Rate',
    panel_type: 'Panel Type',
    gpu: 'Graphics (GPU)',
    operating_system: 'Operating System',
    connectivity: 'Connectivity',
    webcam: 'Webcam',
    ports: 'Ports & Expansion',
    screen_size_in: 'Screen Size',
    display_technology: 'Display Technology',
    resolution: 'Resolution',
    hdr_support: 'HDR Support',
    hdmi_ports: 'HDMI Ports',
    smart_platform: 'Smart TV Platform',
    response_time_ms: 'Response Time',
    noise_cancellation: 'Noise Cancellation',
    driver_size_mm: 'Driver Size',
    bluetooth_version: 'Bluetooth Version',
    audio_codecs: 'Audio Codecs',
    multipoint_pairing: 'Multipoint Bluetooth',
    quick_charge: 'Quick Charge',
    voice_assistant: 'Voice Assistant Support',
    power_source: 'Power Source',
    sensor_included: 'Sensor Included',
    sensor_range_ft: 'Sensor Range',
  };

  if (customLabels[key]) {
    return customLabels[key];
  }

  // Fallback: title case snake_case or camelCase
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

/**
 * Format specification values nicely (e.g., boolean, numbers with units).
 */
const formatSpecValue = (key: string, value: string | number | boolean | null): string => {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (typeof value === 'number') {
    if (key.includes('hours')) return `${value} hrs`;
    if (key.includes('lbs')) return `${value} lbs`;
    if (key.includes('oz')) return `${value} oz`;
    if (key.includes('gb') && !key.includes('storage')) return `${value} GB`;
    if (key === 'storage_gb') return value >= 1000 ? `${value / 1000} TB SSD` : `${value} GB SSD`;
    if (key.includes('hz')) return `${value} Hz`;
    if (key.includes('size_in')) return `${value} inches`;
    if (key.includes('size_mm')) return `${value} mm`;
    if (key.includes('range_ft')) return `${value} ft`;
  }
  return String(value);
};

export const ProductDetailsModal: React.FC<ProductDetailsModalProps> = ({
  product,
  isOpen,
  onClose,
  onSelectForCompare,
  isSelectedForCompare = false,
}) => {
  const [imageError, setImageError] = useState(false);

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen || !product) {
    return null;
  }

  const formattedPrice = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(product.price);

  const canonicalUrl = product.url || `https://www.techbuy.com/site/sku/${product.sku}.p`;

  const specEntries = Object.entries(product.specifications || {});

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto animate-fadeIn"
      role="dialog"
      aria-modal="true"
      aria-labelledby="product-details-modal-title"
    >
      {/* Backdrop */}
      <div
        data-testid="modal-backdrop"
        onClick={onClose}
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        aria-hidden="true"
      />

      {/* Modal Dialog Content Container */}
      <div className="relative bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-3xl w-full max-h-[90vh] flex flex-col z-10 overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-4 bg-slate-50 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-black uppercase tracking-wider bg-blue-100 text-bb-blue px-2.5 py-0.5 rounded-full border border-blue-200">
              {product.brand}
            </span>
            {product.category && (
              <span className="text-xs font-semibold text-gray-500 bg-gray-200/80 px-2.5 py-0.5 rounded-full">
                {product.category}
              </span>
            )}
            <div className="inline-flex items-center gap-1 text-xs text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
              <ShieldCheck className="w-3 h-3 text-bb-blue" aria-hidden="true" />
              <span>SKU: {product.sku}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close product details"
            className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-200/60 rounded-full transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 custom-scrollbar">
          {/* Top Section: Image + Primary Details */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
            {/* Image Box */}
            <div className="relative w-full h-56 bg-slate-100 rounded-xl flex items-center justify-center overflow-hidden border border-gray-200/70 p-4">
              {product.image_url && !imageError ? (
                <img
                  src={product.image_url}
                  alt={product.name}
                  onError={() => setImageError(true)}
                  className="w-full h-full object-contain hover:scale-105 transition-transform"
                />
              ) : (
                <div className="flex flex-col items-center justify-center text-gray-400">
                  <Package className="w-16 h-16 stroke-[1.25]" aria-hidden="true" />
                  <span className="text-xs mt-2 font-medium text-gray-500">
                    TechBuy Retailers Verified Catalog SKU
                  </span>
                </div>
              )}

              {/* Stock Status Badge */}
              <div className="absolute top-3 left-3">
                {product.in_stock ? (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 shadow-xs">
                    <Check className="w-3.5 h-3.5 text-emerald-600" aria-hidden="true" />
                    In Stock
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs font-bold bg-red-100 text-red-800 border border-red-200 shadow-xs">
                    <X className="w-3.5 h-3.5 text-red-600" aria-hidden="true" />
                    Out of Stock
                  </span>
                )}
              </div>
            </div>

            {/* Title & Core Attributes */}
            <div className="space-y-4">
              <h2
                id="product-details-modal-title"
                className="text-lg sm:text-xl font-bold text-gray-900 leading-snug"
              >
                {product.name}
              </h2>

              {/* Rating & Reviews */}
              {product.rating !== null && product.rating !== undefined && (
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <div className="flex items-center text-amber-500">
                    <Star className="w-4 h-4 fill-current" aria-hidden="true" />
                  </div>
                  <span className="font-bold text-gray-900">{product.rating.toFixed(1)}</span>
                  {product.review_count !== null && product.review_count !== undefined && (
                    <span className="text-gray-500 text-xs">
                      ({product.review_count.toLocaleString()} customer reviews)
                    </span>
                  )}
                </div>
              )}

              {/* Price & Grounding Note */}
              <div className="pt-2">
                <span className="text-xs font-semibold uppercase text-gray-500 block">Catalog Price</span>
                <span className="text-3xl font-black text-gray-900 tracking-tight">
                  {formattedPrice}
                </span>
                <p className="text-xs text-gray-500 mt-1">
                  Standard ground shipping or in-store pickup available at TechBuy Retailers.
                </p>
              </div>

              {/* Compare toggle if supported */}
              {onSelectForCompare && (
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={() => onSelectForCompare(product)}
                    className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg font-bold text-xs transition-all shadow-xs cursor-pointer ${
                      isSelectedForCompare
                        ? 'bg-bb-blue text-white ring-2 ring-bb-blue/50'
                        : 'bg-blue-50 text-bb-blue hover:bg-blue-100 border border-blue-200'
                    }`}
                    aria-label={isSelectedForCompare ? 'Remove from comparison' : 'Add to comparison'}
                  >
                    {isSelectedForCompare ? (
                      <>
                        <CheckCheck className="w-4 h-4" aria-hidden="true" />
                        <span>Selected for Comparison</span>
                      </>
                    ) : (
                      <>
                        <Plus className="w-4 h-4" aria-hidden="true" />
                        <span>Add to Comparison</span>
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Full Specifications Section */}
          <div className="pt-4 border-t border-gray-200">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-gray-900">
                Verified Product Specifications
              </h3>
              <span className="text-[11px] font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded border border-blue-100">
                Grounded in Google Cloud BigQuery
              </span>
            </div>

            {specEntries.length > 0 ? (
              <div className="bg-slate-50/70 rounded-xl border border-gray-200 overflow-hidden">
                <dl className="divide-y divide-gray-200/80">
                  {specEntries.map(([key, value], idx) => (
                    <div
                      key={key}
                      className={`grid grid-cols-1 sm:grid-cols-3 px-4 py-3 text-sm ${
                        idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'
                      }`}
                    >
                      <dt className="font-semibold text-gray-700 sm:col-span-1">
                        {formatSpecKey(key)}
                      </dt>
                      <dd className="text-gray-900 sm:col-span-2 mt-1 sm:mt-0 font-medium">
                        {formatSpecValue(key, value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ) : (
              <p className="text-xs text-gray-500 italic">No additional specifications recorded for this SKU.</p>
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 bg-slate-50 border-t border-gray-200 flex flex-wrap items-center justify-between gap-3">
          <a
            href={canonicalUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-bb-blue hover:text-bb-blue-dark hover:underline transition-colors"
          >
            <span>Open TechBuy Catalog Page</span>
            <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
          </a>

          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 font-bold text-xs rounded-lg transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
