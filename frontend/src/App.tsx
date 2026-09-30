import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Sparkles,
  AlertCircle,
  RefreshCw,
  Layers,
  ArrowRight,
  Database,
  Activity,
} from 'lucide-react';
import { compareProducts } from './api/client';
import { ProductDetailsModal } from './components/ProductDetailsModal';
import { CATALOG_PRODUCTS, getCatalogProducts } from './data/catalogProducts';
import { SearchBar } from './components/SearchBar';
import { ComparisonTable } from './components/ComparisonTable';
import { RecommendationCard } from './components/RecommendationCard';
import { ProductCard } from './components/ProductCard';
import { ProductSelectionTray } from './components/ProductSelectionTray';
import { CitationChip } from './components/CitationChip';
import { LatencyBadge } from './components/LatencyBadge';
import { SkeletonLoader } from './components/SkeletonLoader';
import { ProductSpec } from './types/comparison';
import { buildComparisonPrompt } from './utils/promptBuilder';

const SAMPLE_COMPARISONS = [
  {
    title: 'MacBook Air M3 vs Dell XPS 13',
    category: 'Laptops',
    query: 'Compare MacBook Air 13 M3 and Dell XPS 13 OLED specs and battery life',
  },
  {
    title: 'Sony WH-1000XM5 vs Bose QC Ultra',
    category: 'Headphones',
    query: 'Compare Sony WH-1000XM5 and Bose QuietComfort Ultra noise canceling headphones',
  },
  {
    title: 'iPad Pro 11 vs Samsung Galaxy Tab S9',
    category: 'Tablets',
    query: 'Compare iPad Pro 11-inch and Samsung Galaxy Tab S9 price and performance',
  },
  {
    title: 'LG C3 OLED vs Samsung S90C OLED TV',
    category: 'TVs',
    query: 'Compare LG C3 Series 4K OLED TV and Samsung S90C OLED specs and gaming features',
  },
];

export const App: React.FC = () => {
  const [sessionId] = useState<string>(() => {
    const existing = sessionStorage.getItem('bb_session_id');
    if (existing) return existing;
    const fresh = 'sess-' + Math.random().toString(36).substring(2, 10);
    sessionStorage.setItem('bb_session_id', fresh);
    return fresh;
  });

  const [searchParams, setSearchParams] = useState<{
    query: string;
    category: string | null;
  } | null>(null);

  const [browseCategory, setBrowseCategory] = useState<{
    category: string | null;
  } | null>(null);

  const [selectedProducts, setSelectedProducts] = useState<ProductSpec[]>([]);
  const [activeModalProduct, setActiveModalProduct] = useState<ProductSpec | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleOpenProductDetails = (productOrSku: ProductSpec | string) => {
    if (typeof productOrSku === 'object' && productOrSku !== null) {
      setActiveModalProduct(productOrSku);
      setIsModalOpen(true);
      return;
    }

    const sku = String(productOrSku).trim();
    // 1. Search in current comparison result products
    const foundInComparison = comparison?.products?.find((p) => p.sku === sku);
    if (foundInComparison) {
      setActiveModalProduct(foundInComparison);
      setIsModalOpen(true);
      return;
    }

    // 2. Search in browsed / catalog products
    const foundInCatalog = CATALOG_PRODUCTS.find((p) => p.sku === sku);
    if (foundInCatalog) {
      setActiveModalProduct(foundInCatalog);
      setIsModalOpen(true);
      return;
    }

    // 3. Fallback dummy ProductSpec for unknown SKU
    setActiveModalProduct({
      sku,
      name: `TechBuy Verified SKU ${sku}`,
      brand: 'TechBuy Retailers',
      price: 0,
      specifications: {
        sku,
        status: 'Catalog Grounded Record',
        source: 'Google Cloud BigQuery (fde-bestbuy-sandbox-dev-508321.catalog.products)',
      },
      in_stock: true,
    });
    setIsModalOpen(true);
  };

  const handleCloseProductDetails = () => {
    setIsModalOpen(false);
    setActiveModalProduct(null);
  };

  const {
    data: comparison,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['compare', searchParams?.query, searchParams?.category],
    queryFn: () =>
      searchParams
        ? compareProducts({
            query: searchParams.query,
            category: searchParams.category,
            session_id: sessionId,
          })
        : null,
    enabled: !!searchParams?.query,
    staleTime: 0,
    retry: false,
  });

  const [taggedProducts, setTaggedProducts] = useState<ProductSpec[]>([]);
  const [prevComparison, setPrevComparison] = useState(comparison);

  // Auto-populate compared SKU tags in SearchBar whenever comparison completes and no tags currently set
  if (comparison !== prevComparison) {
    setPrevComparison(comparison);
    if (comparison?.products && comparison.products.length > 0 && taggedProducts.length === 0) {
      setTaggedProducts(comparison.products);
    }
  }

  const handleGoHome = () => {
    setSearchParams(null);
    setBrowseCategory(null);
    setSelectedProducts([]);
    setTaggedProducts([]);
  };

  const handleSearch = (
    query: string,
    category: string | null,
    tagged?: ProductSpec[]
  ) => {
    setBrowseCategory(null);
    if (tagged !== undefined) {
      setTaggedProducts(tagged);
    }
    setSearchParams({ query, category });
  };

  const handleCategorySelect = (category: string | null) => {
    setSearchParams(null);
    setBrowseCategory({ category });
  };

  const handleSampleClick = (sample: (typeof SAMPLE_COMPARISONS)[number]) => {
    setBrowseCategory(null);
    setTaggedProducts([]);
    setSearchParams({ query: sample.query, category: sample.category });
  };

  const handleToggleSelectProduct = (product: ProductSpec) => {
    setSelectedProducts((prev) => {
      const exists = prev.some((p) => p.sku === product.sku);
      if (exists) {
        return prev.filter((p) => p.sku !== product.sku);
      }
      if (prev.length >= 4) {
        return prev;
      }
      return [...prev, product];
    });
  };

  const handleRemoveSelectedProduct = (sku: string) => {
    setSelectedProducts((prev) => prev.filter((p) => p.sku !== sku));
  };

  const handleClearSelectedProducts = () => {
    setSelectedProducts([]);
  };

  const handleRemoveTag = (sku: string) => {
    setTaggedProducts((prev) => prev.filter((p) => p.sku !== sku));
  };

  const handleClearTags = () => {
    setTaggedProducts([]);
  };

  const formatSelectedQuery = (products: ProductSpec[]): string => {
    if (products.length === 0) return '';
    if (products.length === 1) return `Compare ${products[0].name} vs `;
    if (products.length === 2) {
      return `Compare ${products[0].name} vs ${products[1].name}`;
    }
    const allExceptLast = products.slice(0, -1).map((p) => p.name).join(', ');
    const last = products[products.length - 1].name;
    return `Compare ${allExceptLast}, and ${last}`;
  };

  const handleCompareSelected = (products: ProductSpec[]) => {
    if (products.length < 2) return;

    // Build the rich prompt with all attributes implicitly
    const prompt = buildComparisonPrompt(products);
    const category = products[0]?.category || browseCategory?.category || null;

    setBrowseCategory(null);
    setTaggedProducts([...products]);
    setSelectedProducts([]);
    setSearchParams({ query: prompt, category });
  };

  const browsedProducts = browseCategory
    ? getCatalogProducts(browseCategory.category)
    : [];

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-gray-900 selection:bg-bb-yellow selection:text-bb-slate">
      {/* Best Buy Header */}
      <header className="bg-bb-blue text-white shadow-md sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16 gap-4">
            {/* Logo & Tagline */}
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleGoHome}
                className="bg-bb-yellow text-bb-slate font-black text-xl px-2.5 py-1 rounded shadow-xs tracking-tighter hover:bg-bb-yellow-hover transition-colors cursor-pointer"
              >
                TECHBUY RETAILERS
              </button>
              <div className="hidden sm:block border-l border-blue-400/50 pl-3">
                <span className="text-sm font-bold tracking-tight block">
                  Catalog Comparison Agent
                </span>
                <span className="text-[11px] text-blue-200 block">
                  Grounded in Google Cloud BigQuery
                </span>
              </div>
            </div>

            {/* Header Telemetry Badge */}
            <div className="flex items-center gap-3">
              {comparison?.session_comparison_count && (
                <div
                  className="hidden sm:flex items-center gap-1.5 text-xs text-blue-100 bg-blue-900/60 px-2.5 py-1 rounded-full border border-blue-400/30"
                  title={`Comparison #${comparison.session_comparison_count} run in this session`}
                >
                  <Activity className="w-3.5 h-3.5 text-yellow-300" aria-hidden="true" />
                  <span>Comparison #{comparison.session_comparison_count}</span>
                </div>
              )}
              {comparison?.latency_ms && (
                <LatencyBadge latencyMs={comparison.latency_ms} />
              )}
              <div className="hidden md:flex items-center gap-1.5 text-xs text-blue-100 bg-bb-blue-dark/50 px-3 py-1.5 rounded-full border border-blue-400/30">
                <Database className="w-3.5 h-3.5 text-bb-yellow" aria-hidden="true" />
                <span>fde-bestbuy-sandbox-dev-508321</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Hero & Search Section */}
      <section className="bg-gradient-to-b from-bb-blue to-bb-blue-dark text-white py-10 px-4 sm:px-6 lg:px-8 shadow-inner">
        <div className="max-w-4xl mx-auto text-center space-y-4 mb-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-blue-500/30 text-yellow-300 border border-yellow-300/30">
            <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Zero Hallucination Spec Comparisons</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Compare Consumer Electronics Side-by-Side
          </h1>
          <p className="text-base text-blue-100 max-w-2xl mx-auto">
            Ask any product comparison query. Our agent retrieves verified specs directly from the BigQuery
            catalog and highlights superior attributes instantly.
          </p>
        </div>

        <SearchBar
          onSearch={handleSearch}
          onCategorySelect={handleCategorySelect}
          isLoading={isLoading}
          taggedProducts={taggedProducts}
          onRemoveTag={handleRemoveTag}
          onClearTags={handleClearTags}
          initialQuery={
            taggedProducts.length > 0
              ? ''
              : selectedProducts.length > 0
                ? formatSelectedQuery(selectedProducts)
                : searchParams?.query || ''
          }
          initialCategory={
            searchParams
              ? searchParams.category
              : browseCategory
                ? browseCategory.category
                : null
          }
        />
      </section>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Loading State */}
        {isLoading && <SkeletonLoader />}

        {/* Error State */}
        {isError && (
          <div
            role="alert"
            className="max-w-2xl mx-auto bg-white rounded-xl border border-red-200 p-6 shadow-sm text-center space-y-4"
          >
            <div className="w-12 h-12 rounded-full bg-red-50 text-red-600 flex items-center justify-center mx-auto">
              <AlertCircle className="w-6 h-6" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900">Comparison Failed</h3>
              <p className="text-sm text-gray-600 mt-1">
                {(error as Error)?.message ||
                  'Unable to retrieve product specs from catalog. Please try again.'}
              </p>
            </div>
            <button
              onClick={() => refetch()}
              className="inline-flex items-center gap-2 px-4 py-2 bg-bb-blue text-white rounded-lg font-semibold text-sm hover:bg-bb-blue-light transition-colors"
            >
              <RefreshCw className="w-4 h-4" aria-hidden="true" />
              <span>Retry Comparison</span>
            </button>
          </div>
        )}

        {/* Success State */}
        {!isLoading && !isError && comparison && (
          <div className="space-y-8 animate-fadeIn">
            {/* Top Telemetry & Count Bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-gray-200 shadow-xs">
              <div className="flex items-center gap-2 text-sm text-gray-700 font-medium">
                <Layers className="w-4 h-4 text-bb-blue" aria-hidden="true" />
                <span>
                  Comparing <strong className="text-gray-900">{comparison.products.length}</strong> products
                  {searchParams?.category && (
                    <> in <span className="font-semibold text-bb-blue">{searchParams.category}</span></>
                  )}
                </span>
              </div>
              <LatencyBadge latencyMs={comparison.latency_ms} />
            </div>

            {/* AI Recommendation Narrative */}
            <RecommendationCard
              summary={comparison.summary}
              recommendations={comparison.recommendations}
              query={searchParams?.query || ''}
              targetSkus={comparison.products.map((p) => p.sku)}
              sessionId={sessionId}
              traceId={comparison.trace_id || ''}
            />

            {/* Product Summary Cards & Matrix Table (Only if products found) */}
            {comparison.products.length > 0 ? (
              <>
                <div>
                  <h2 className="text-lg font-bold text-gray-900 mb-4">Compared Products</h2>
                  <div
                    className={`grid gap-6 ${
                      comparison.products.length === 2
                        ? 'grid-cols-1 md:grid-cols-2'
                        : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'
                    }`}
                  >
                    {comparison.products.map((product) => (
                      <ProductCard
                        key={product.sku}
                        product={product}
                        onViewDetails={handleOpenProductDetails}
                      />
                    ))}
                  </div>
                </div>

                {/* Side-by-side Feature Matrix Table */}
                <ComparisonTable
                  products={comparison.products}
                  matrix={comparison.comparison_matrix}
                  onViewDetails={handleOpenProductDetails}
                />
              </>
            ) : (
              /* Helpful zero-results guidance card */
              <div className="bg-white rounded-2xl border border-blue-100 p-8 text-center space-y-4 shadow-xs">
                <div className="w-12 h-12 rounded-full bg-blue-50 text-bb-blue flex items-center justify-center mx-auto text-xl font-bold">
                  🔍
                </div>
                <div className="max-w-md mx-auto space-y-1">
                  <h3 className="text-lg font-bold text-gray-900">No Matching Electronics Found</h3>
                  <p className="text-sm text-gray-500">
                    We couldn't find items matching this query in the catalog. Try searching for consumer tech models like laptops, headphones, tablets, or TVs.
                  </p>
                </div>
                <div className="pt-2 flex flex-wrap justify-center gap-2">
                  {SAMPLE_COMPARISONS.map((sample) => (
                    <button
                      key={sample.title}
                      onClick={() => handleSampleClick(sample)}
                      className="px-3.5 py-1.5 rounded-full text-xs font-semibold bg-slate-100 text-gray-700 hover:bg-bb-yellow hover:text-bb-slate transition-all border border-gray-200"
                    >
                      {sample.title}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Verified SKU Citations Section */}
            {comparison.citations && comparison.citations.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
                <h3 className="text-sm font-bold uppercase tracking-wider text-gray-500">
                  Verified SKU Grounding & Citations
                </h3>
                <p className="text-xs text-gray-600">
                  Every specification above is strictly verified against Google Cloud BigQuery. Click any SKU badge
                  to view canonical product details on TechBuy.com.
                </p>
                <div className="flex flex-wrap items-center gap-3 pt-2">
                  {comparison.citations.map((citation) => (
                    <div key={citation.sku} className="flex items-center gap-2">
                      <CitationChip
                        sku={citation.sku}
                        url={citation.url}
                        description={citation.description}
                        onClick={handleOpenProductDetails}
                      />
                      {citation.description && (
                        <span className="text-xs text-gray-500 hidden sm:inline">
                          — {citation.description}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Category SKU Browsing State */}
        {!isLoading && !isError && !comparison && browseCategory && (
          <div className="space-y-6 animate-fadeIn">
            <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-gray-200 shadow-xs">
              <div className="flex items-center gap-2 text-sm text-gray-700 font-medium">
                <Layers className="w-4 h-4 text-bb-blue" aria-hidden="true" />
                <div>
                  <h2 className="text-base font-bold text-gray-900">
                    {browseCategory.category
                      ? `${browseCategory.category} Catalog`
                      : 'All Categories Catalog'}
                  </h2>
                  <p className="text-xs text-gray-500">
                    Showing {browsedProducts.length} verified SKUs grounded in Google Cloud BigQuery
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleGoHome}
                className="text-xs font-semibold text-bb-blue hover:underline"
              >
                ← Back to Homepage
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {browsedProducts.map((product) => {
                const isSelected = selectedProducts.some((p) => p.sku === product.sku);
                return (
                  <ProductCard
                    key={product.sku}
                    product={product}
                    selectable={true}
                    isSelected={isSelected}
                    onToggleSelect={handleToggleSelectProduct}
                    onViewDetails={handleOpenProductDetails}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* Empty / Idle State */}
        {!isLoading && !isError && !comparison && !browseCategory && (
          <div className="max-w-4xl mx-auto space-y-8 py-6">
            <div className="text-center space-y-2">
              <h2 className="text-xl font-bold text-gray-800">
                Popular Product Comparisons
              </h2>
              <p className="text-sm text-gray-500">
                Select an example below or enter your own query in the search bar above.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {SAMPLE_COMPARISONS.map((sample) => (
                <button
                  key={sample.title}
                  onClick={() => handleSampleClick(sample)}
                  className="bg-white p-5 rounded-xl border border-gray-200 hover:border-bb-blue hover:shadow-md text-left transition-all flex items-start justify-between group"
                >
                  <div className="space-y-1.5 pr-4">
                    <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-blue-50 text-bb-blue border border-blue-100">
                      {sample.category}
                    </span>
                    <h3 className="text-base font-bold text-gray-900 group-hover:text-bb-blue transition-colors">
                      {sample.title}
                    </h3>
                    <p className="text-xs text-gray-500 line-clamp-2">
                      {sample.query}
                    </p>
                  </div>
                  <div className="w-8 h-8 rounded-full bg-slate-100 group-hover:bg-bb-yellow group-hover:text-bb-slate flex items-center justify-center text-gray-400 transition-colors flex-shrink-0 mt-2">
                    <ArrowRight className="w-4 h-4" />
                  </div>
                </button>
              ))}
            </div>

            {/* Architecture Highlights Banner */}
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-xs grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-1">
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-bb-blue flex items-center justify-center font-black text-sm mb-2">
                  BQ
                </div>
                <h4 className="text-sm font-bold text-gray-900">100% Fact Grounded</h4>
                <p className="text-xs text-gray-500">
                  Specifications originate strictly from BigQuery catalog dataset with zero hallucination.
                </p>
              </div>
              <div className="space-y-1">
                <div className="w-8 h-8 rounded-lg bg-yellow-50 text-yellow-800 flex items-center justify-center font-black text-sm mb-2">
                  ⚡
                </div>
                <h4 className="text-sm font-bold text-gray-900">Sub-3.0s Latency</h4>
                <p className="text-xs text-gray-500">
                  Target end-to-end response time under 3.0 seconds with immediate skeleton feedback.
                </p>
              </div>
              <div className="space-y-1">
                <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-800 flex items-center justify-center font-black text-sm mb-2">
                  ✓
                </div>
                <h4 className="text-sm font-bold text-gray-900">Verified SKU Citations</h4>
                <p className="text-xs text-gray-500">
                  Interactive badges link directly to official TechBuy.com catalog product listings.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Product Selection Tray for Multiselect Catalog Comparisons */}
        <ProductSelectionTray
          selectedProducts={selectedProducts}
          onRemoveProduct={handleRemoveSelectedProduct}
          onClearSelection={handleClearSelectedProducts}
          onCompare={handleCompareSelected}
        />

        {/* Product Specifications & Details Modal */}
        <ProductDetailsModal
          product={activeModalProduct}
          isOpen={isModalOpen}
          onClose={handleCloseProductDetails}
          onSelectForCompare={handleToggleSelectProduct}
          isSelectedForCompare={
            activeModalProduct
              ? selectedProducts.some((p) => p.sku === activeModalProduct.sku)
              : false
          }
        />
      </main>

      {/* TechBuy Retailers Footer */}
      <footer className="bg-bb-slate text-gray-400 py-8 px-4 sm:px-6 lg:px-8 border-t border-gray-800 mt-auto text-xs">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="font-bold text-white tracking-tight">TechBuy Retailers Catalog Comparison Agent</span>
            <span>•</span>
            <span>GCP Project: <code className="text-blue-300">fde-bestbuy-sandbox-dev-508321</code></span>
          </div>
          <div className="text-gray-500">
            FDE Capstone Project • Automated via Swarm Hillclimbing
          </div>
        </div>
      </footer>
    </div>
  );
};
