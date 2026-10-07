import React from 'react';
import { ExternalLink, ShieldCheck } from 'lucide-react';

export interface CitationChipProps {
  sku: string;
  url?: string | null;
  description?: string | null;
  className?: string;
  showIcon?: boolean;
  onClick?: (sku: string) => void;
}

/**
 * Interactive SKU citation chip badge verifying catalog grounding.
 * Links directly to TechBuy.com product listing or opens in-app ProductDetailsModal.
 */
export const CitationChip: React.FC<CitationChipProps> = ({
  sku,
  url,
  description,
  className = '',
  showIcon = true,
  onClick,
}) => {
  const canonicalUrl = url || `https://www.techbuy.com/site/sku/${sku}.p`;
  const titleText = description || `Verified TechBuy Retailers SKU ${sku} in BigQuery catalog`;
  const ariaLabelText = `View product details for SKU ${sku} on TechBuy.com`;
  const baseClasses = `inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium shrink-0 whitespace-nowrap 
    bg-blue-50 text-blue-800 border border-blue-200 
    hover:bg-blue-100 hover:text-blue-900 transition-colors 
    focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-bb-blue ${className}`;

  if (onClick) {
    return (
      <button
        type="button"
        onClick={() => onClick(sku)}
        title={titleText}
        aria-label={ariaLabelText}
        className={`${baseClasses} cursor-pointer`}
      >
        <ShieldCheck className="w-3 h-3 text-bb-blue shrink-0" aria-hidden="true" />
        <span className="whitespace-nowrap">[SKU: {sku}]</span>
        {showIcon && (
          <ExternalLink className="w-2.5 h-2.5 text-blue-500 opacity-80 shrink-0" aria-hidden="true" />
        )}
      </button>
    );
  }

  return (
    <a
      href={canonicalUrl}
      target="_blank"
      rel="noopener noreferrer"
      title={titleText}
      aria-label={ariaLabelText}
      className={baseClasses}
    >
      <ShieldCheck className="w-3 h-3 text-bb-blue shrink-0" aria-hidden="true" />
      <span className="whitespace-nowrap">[SKU: {sku}]</span>
      {showIcon && (
        <ExternalLink className="w-2.5 h-2.5 text-blue-500 opacity-80 shrink-0" aria-hidden="true" />
      )}
    </a>
  );
};
