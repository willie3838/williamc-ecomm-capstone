import React from 'react';
import { Award, Check, X, HelpCircle } from 'lucide-react';
import { MatrixRow, ProductSpec } from '../types/comparison';
import { CitationChip } from './CitationChip';

export interface ComparisonTableProps {
  products: ProductSpec[];
  matrix: MatrixRow[];
  className?: string;
}

/**
 * Side-by-side feature comparison matrix dynamically comparing product specifications.
 * Highlights winning/superior attributes with distinct badge styling.
 */
export const ComparisonTable: React.FC<ComparisonTableProps> = ({
  products,
  matrix,
  className = '',
}) => {
  if (!products || products.length === 0) {
    return null;
  }

  if (!matrix || matrix.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-500">
        <HelpCircle className="w-8 h-8 mx-auto text-gray-400 mb-2" aria-hidden="true" />
        <p className="font-medium text-gray-700">No detailed comparison specs available for these items.</p>
        <p className="text-sm text-gray-500 mt-1">Try refining your comparison query with specific product models.</p>
      </div>
    );
  }

  const renderValue = (val: string | number | boolean | null | undefined) => {
    if (val === null || val === undefined || val === '') {
      return <span className="text-gray-400 font-normal italic">—</span>;
    }
    if (typeof val === 'boolean') {
      return val ? (
        <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold text-xs">
          <Check className="w-4 h-4 text-emerald-600" aria-hidden="true" /> Yes
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-gray-500 text-xs">
          <X className="w-4 h-4 text-gray-400" aria-hidden="true" /> No
        </span>
      );
    }
    return <span className="text-gray-900 font-medium text-sm">{String(val)}</span>;
  };

  return (
    <div
      className={`bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col ${className}`}
    >
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-gray-900">Side-by-Side Specification Matrix</h3>
          <p className="text-xs text-gray-500">
            Specifications extracted directly from BigQuery catalog. Winning specs are highlighted.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-semibold text-bb-blue bg-blue-50 px-3 py-1 rounded-full border border-blue-100">
          <Award className="w-3.5 h-3.5 text-amber-500" aria-hidden="true" />
          <span>Top Spec Winner Highlighted</span>
        </div>
      </div>

      <div className="overflow-x-auto custom-scrollbar">
        <table className="w-full text-left border-collapse min-w-[650px]">
          <thead>
            <tr className="bg-slate-50 border-b border-gray-200">
              <th className="py-4 px-6 text-xs font-bold uppercase tracking-wider text-gray-600 w-1/4 sticky left-0 bg-slate-50 z-10 border-r border-gray-200 shadow-xs">
                Specification
              </th>
              {products.map((product) => (
                <th
                  key={product.sku}
                  className="py-4 px-6 text-left align-top min-w-[200px]"
                >
                  <div className="space-y-1.5">
                    <span className="text-xs font-bold uppercase tracking-wider text-bb-blue block">
                      {product.brand}
                    </span>
                    <h4 className="text-sm font-bold text-gray-900 line-clamp-2 leading-tight">
                      {product.name}
                    </h4>
                    <div className="flex items-center justify-between pt-1">
                      <span className="text-base font-extrabold text-gray-900">
                        {new Intl.NumberFormat('en-US', {
                          style: 'currency',
                          currency: 'USD',
                        }).format(product.price)}
                      </span>
                      <CitationChip sku={product.sku} url={product.url} />
                    </div>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {matrix.map((row, idx) => (
              <tr
                key={row.feature || idx}
                className={idx % 2 === 0 ? 'bg-white hover:bg-slate-50/60' : 'bg-slate-50/30 hover:bg-slate-50'}
              >
                {/* Feature Label Column (Sticky) */}
                <td className="py-3.5 px-6 font-semibold text-sm text-gray-800 sticky left-0 bg-inherit z-10 border-r border-gray-200 shadow-xs">
                  {row.feature}
                </td>

                {/* Values per Product */}
                {products.map((product) => {
                  const isWinner = row.winner_sku === product.sku;
                  const rawVal = row.values?.[product.sku];

                  return (
                    <td
                      key={`${row.feature}-${product.sku}`}
                      className={`py-3.5 px-6 align-middle transition-colors ${
                        isWinner
                          ? 'bg-emerald-50/70 border-emerald-200 font-semibold'
                          : ''
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex-1">{renderValue(rawVal)}</div>
                        {isWinner && (
                          <span
                            className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-tight bg-emerald-600 text-white shadow-xs flex-shrink-0"
                            aria-label="Superior specification"
                            title="Superior specification grounded in catalog specs"
                          >
                            <Award className="w-3 h-3" aria-hidden="true" />
                            Winner
                          </span>
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
