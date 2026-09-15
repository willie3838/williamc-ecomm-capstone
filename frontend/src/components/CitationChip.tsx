import React from 'react';
import { ExternalLink, ShieldCheck } from 'lucide-react';

export interface CitationChipProps {
  sku: string;
  url?: string | null;
  description?: string | null;
  className?: string;
  showIcon?: boolean;
}

/**
 * Interactive SKU citation chip badge verifying catalog grounding.
 * Links directly to BestBuy.com product listing.
 */
export const CitationChip: React.FC<CitationChipProps> = ({
  sku,
  url,
  description,
  className = '',
  showIcon = true,
}) => {
  const canonicalUrl = url || `https://www.bestbuy.com/site/sku/${sku}.p`;

  return (
    <a
      href={canonicalUrl}
      target="_blank"
      rel="noopener noreferrer"
      title={description || `Verified Best Buy SKU ${sku} in BigQuery catalog`}
      aria-label={`View product details for SKU ${sku} on BestBuy.com`}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium 
        bg-blue-50 text-blue-800 border border-blue-200 
        hover:bg-blue-100 hover:text-blue-900 transition-colors 
        focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-bb-blue ${className}`}
    >
      <ShieldCheck className="w-3 h-3 text-bb-blue flex-shrink-0" aria-hidden="true" />
      <span>[SKU: {sku}]</span>
      {showIcon && (
        <ExternalLink className="w-2.5 h-2.5 text-blue-500 opacity-80 flex-shrink-0" aria-hidden="true" />
      )}
    </a>
  );
};
