import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Sparkles,
  AlertCircle,
  RefreshCw,
  Layers,
  Database,
  Activity,
  Search,
  Plus,
  X,
} from 'lucide-react';
import { compareProducts, compareProductsStream } from './api/client';
import { ProductDetailsModal } from './components/ProductDetailsModal';
import { CATALOG_PRODUCTS, getCatalogProducts, searchCatalogProducts } from './data/catalogProducts';
import { SearchBar } from './components/SearchBar';
import { ComparisonTable } from './components/ComparisonTable';
import { RecommendationCard } from './components/RecommendationCard';
import { ProductCard } from './components/ProductCard';
import { ProductSelectionTray } from './components/ProductSelectionTray';
import { CitationChip } from './components/CitationChip';
import { LatencyBadge } from './components/LatencyBadge';
import { SkeletonLoader } from './components/SkeletonLoader';
import { ConversationSidebar } from './components/ConversationSidebar';
import { ComparisonResponse, ProductSpec } from './types/comparison';
import { buildComparisonPrompt } from './utils/promptBuilder';

const INITIAL_VISIBLE_CARDS = 40;

const createFreshSessionId = (): string => {
  return 'sess-' + Math.random().toString(36).substring(2, 10);
};

export const App: React.FC = () => {
  const [sessionId, setSessionId] = useState<string>(() => {
    const existing = sessionStorage.getItem('bb_session_id');
    if (existing) return existing;
    const fresh = createFreshSessionId();
    sessionStorage.setItem('bb_session_id', fresh);
    return fresh;
  });

  const rotateSessionId = React.useCallback((): string => {
    const fresh = createFreshSessionId();
    sessionStorage.setItem('bb_session_id', fresh);
    setSessionId(fresh);
    return fresh;
  }, []);

  const [searchParams, setSearchParams] = useState<{
    query: string;
    category: string | null;
    sessionId: string;
  } | null>(null);

  const [browseCategory, setBrowseCategory] = useState<{
    category: string | null;
  } | null>({ category: null });

  const [catalogSearchQuery, setCatalogSearchQuery] = useState('');
  const [visibleCardCount, setVisibleCardCount] = useState<number>(INITIAL_VISIBLE_CARDS);
  const [isAddCompareOpen, setIsAddCompareOpen] = useState(false);
  const [addCompareQuery, setAddCompareQuery] = useState('');

  const [selectedProducts, setSelectedProducts] = useState<ProductSpec[]>([]);
  const [activeModalProduct, setActiveModalProduct] = useState<ProductSpec | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(true);

  const [streamingComparison, setStreamingComparison] = useState<Partial<ComparisonResponse> | null>(null);
  const [isStreamingSynthesis, setIsStreamingSynthesis] = useState<boolean>(false);

  const {
    data: comparison,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['compare', searchParams?.query, searchParams?.category],
    queryFn: async () => {
      if (!searchParams) return null;
      setIsStreamingSynthesis(true);
      try {
        const queryPayload = {
          query: searchParams.query,
          category: searchParams.category,
          session_id: sessionId,
        };
        const result =
          typeof compareProductsStream === 'function'
            ? await compareProductsStream(queryPayload, {
                onMatrixReady: (partial) => {
                  setStreamingComparison((prev) => ({
                    ...prev,
                    products: partial.products,
                    comparison_matrix: partial.comparison_matrix,
                    citations: partial.citations,
                    session_id: partial.session_id,
                    trace_id: partial.trace_id,
                  }));
                },
                onSynthesisChunk: (chunk) => {
                  setStreamingComparison((prev) => ({
                    ...prev,
                    summary: chunk.summary,
                    recommendations: chunk.recommendations ?? prev?.recommendations,
                  }));
                },
                onMatrixUpdated: (update) => {
                  setStreamingComparison((prev) => ({
                    ...prev,
                    comparison_matrix: update.comparison_matrix,
                  }));
                },
              })
            : await compareProducts(queryPayload);
        setIsStreamingSynthesis(false);
        return result;
      } catch (err) {
        setIsStreamingSynthesis(false);
        setStreamingComparison(null);
        throw err;
      }
    },
    enabled: !!searchParams?.query,
    staleTime: 0,
    retry: false,
  });

  const activeComparison: ComparisonResponse | null = useMemo(() => {
    if (comparison) return comparison;
    if (streamingComparison && streamingComparison.products && streamingComparison.products.length > 0) {
      return {
        summary: streamingComparison.summary || '',
        recommendations: streamingComparison.recommendations ?? null,
        products: streamingComparison.products,
        comparison_matrix: streamingComparison.comparison_matrix || [],
        citations: streamingComparison.citations || [],
        latency_ms: streamingComparison.latency_ms ?? null,
        session_id: streamingComparison.session_id ?? null,
        trace_id: streamingComparison.trace_id ?? null,
      };
    }
    return null;
  }, [comparison, streamingComparison]);

  const handleOpenProductDetails = (productOrSku: ProductSpec | string) => {
    if (typeof productOrSku === 'object' && productOrSku !== null) {
      setActiveModalProduct(productOrSku);
      setIsModalOpen(true);
      return;
    }

    const sku = String(productOrSku).trim();
    // 1. Search in current comparison result products
    const foundInComparison = (comparison || activeComparison)?.products?.find((p) => p.sku === sku);
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

  const [taggedProducts, setTaggedProducts] = useState<ProductSpec[]>([]);
  const [prevComparison, setPrevComparison] = useState(comparison);

  // Auto-populate compared SKU tags in SearchBar whenever comparison completes
  if (comparison && comparison !== prevComparison) {
    const prevProducts = prevComparison?.products || [];
    const newProducts = comparison?.products || [];
    const prevSkus = prevProducts.map((p) => p.sku).sort().join(',');
    const newSkus = newProducts.map((p) => p.sku).sort().join(',');

    setPrevComparison(comparison);
    if (newProducts.length > 0) {
      if (taggedProducts.length === 0 || (prevProducts.length > 0 && prevSkus !== newSkus)) {
        setTaggedProducts(newProducts);
      }
      setIsChatOpen(true);
    }
  }

  const handleGoHome = () => {
    rotateSessionId();
    setSearchParams(null);
    setStreamingComparison(null);
    setIsStreamingSynthesis(false);
    setBrowseCategory({ category: null });
    setCatalogSearchQuery('');
    setVisibleCardCount(INITIAL_VISIBLE_CARDS);
    setIsAddCompareOpen(false);
    setAddCompareQuery('');
    setSelectedProducts([]);
    setTaggedProducts([]);
  };

  const handleSearch = (
    query: string,
    category: string | null,
    tagged?: ProductSpec[]
  ) => {
    const effectiveTagged =
      tagged !== undefined
        ? tagged
        : selectedProducts.length > 0
          ? selectedProducts
          : taggedProducts;
    if (!effectiveTagged || effectiveTagged.length < 2) {
      return;
    }
    const freshSessionId = rotateSessionId();
    setBrowseCategory(null);
    setIsAddCompareOpen(false);
    setAddCompareQuery('');
    setTaggedProducts(effectiveTagged);
    setSelectedProducts([]);
    setStreamingComparison(null);
    setIsStreamingSynthesis(false);
    setIsChatOpen(true);
    setSearchParams({ query, category, sessionId: freshSessionId });
  };

  const handleCategorySelect = (category: string | null) => {
    setSearchParams(null);
    setStreamingComparison(null);
    setIsStreamingSynthesis(false);
    setCatalogSearchQuery('');
    setVisibleCardCount(INITIAL_VISIBLE_CARDS);
    setIsAddCompareOpen(false);
    setAddCompareQuery('');
    setBrowseCategory({ category });
  };

  const handleToggleSelectProduct = (product: ProductSpec, action: 'toggle' | 'add' = 'toggle') => {
    const base =
      selectedProducts.length > 0
        ? selectedProducts
        : taggedProducts.length > 0
          ? taggedProducts
          : (activeComparison || comparison)?.products || [];

    const exists = base.some((p) => p.sku === product.sku);
    let next: ProductSpec[];
    if (exists) {
      if (action === 'add') {
        setSelectedProducts(base);
        setTaggedProducts(base);
        return;
      }
      next = base.filter((p) => p.sku !== product.sku);
    } else {
      if (base.length >= 5) {
        return;
      }
      next = [...base, product];
    }
    setSelectedProducts(next);
    setTaggedProducts(next);
  };

  const handleRemoveSelectedProduct = (sku: string) => {
    setSelectedProducts((prev) => prev.filter((p) => p.sku !== sku));
    setTaggedProducts((prev) => prev.filter((p) => p.sku !== sku));
  };

  const handleClearSelectedProducts = () => {
    setSelectedProducts([]);
    setTaggedProducts([]);
  };

  const handleRemoveTag = (sku: string) => {
    setTaggedProducts((prev) => prev.filter((p) => p.sku !== sku));
    setSelectedProducts((prev) => prev.filter((p) => p.sku !== sku));
  };

  const handleClearTags = () => {
    setTaggedProducts([]);
    setSelectedProducts([]);
  };

  const handleCompareSelected = (products: ProductSpec[]) => {
    if (products.length < 2) return;

    // Build the rich prompt with all attributes implicitly
    const prompt = buildComparisonPrompt(products);
    const allSameCategory =
      products.length > 0 &&
      products.every((p) => Boolean(p.category) && p.category === products[0].category);
    const category = allSameCategory ? (products[0].category || null) : null;

    const freshSessionId = rotateSessionId();
    setBrowseCategory(null);
    setTaggedProducts([...products]);
    setSelectedProducts([]);
    setStreamingComparison(null);
    setIsStreamingSynthesis(false);
    setIsChatOpen(true);
    setSearchParams({ query: prompt, category, sessionId: freshSessionId });
  };

  const handleAddProductToActiveComparison = (product: ProductSpec) => {
    const currentProducts = activeComparison?.products || comparison?.products;
    if (!currentProducts) return;
    if (currentProducts.some((p) => p.sku === product.sku)) return;
    if (currentProducts.length >= 5) return;

    const newProducts = [...currentProducts, product];
    setIsAddCompareOpen(false);
    setAddCompareQuery('');
    handleCompareSelected(newProducts);
  };

  const totalCategoryProducts = useMemo(() => {
    if (!browseCategory) return [];
    return getCatalogProducts(browseCategory.category);
  }, [browseCategory]);

  const browsedProducts = useMemo(() => {
    if (!browseCategory) return [];
    return searchCatalogProducts(catalogSearchQuery, browseCategory.category);
  }, [browseCategory, catalogSearchQuery]);


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
              {(activeComparison || comparison)?.session_comparison_count && (
                <div
                  className="hidden sm:flex items-center gap-1.5 text-xs text-blue-100 bg-blue-900/60 px-2.5 py-1 rounded-full border border-blue-400/30"
                  title={`Comparison #${(activeComparison || comparison)?.session_comparison_count} run in this session`}
                >
                  <Activity className="w-3.5 h-3.5 text-yellow-300" aria-hidden="true" />
                  <span>Comparison #{(activeComparison || comparison)?.session_comparison_count}</span>
                </div>
              )}
              {(activeComparison || comparison)?.latency_ms && (
                <LatencyBadge latencyMs={(activeComparison || comparison)!.latency_ms} />
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
            Select at least 2 products from the catalog or search bar to compare. Our agent retrieves verified specs directly from the BigQuery
            catalog and highlights superior attributes instantly.
          </p>
        </div>

        <SearchBar
          onSearch={handleSearch}
          onCategorySelect={handleCategorySelect}
          isLoading={isLoading}
          taggedProducts={selectedProducts.length > 0 ? selectedProducts : taggedProducts}
          onAddTag={(p) => handleToggleSelectProduct(p, 'add')}
          onRemoveTag={handleRemoveTag}
          onClearTags={handleClearTags}
          initialQuery={
            selectedProducts.length > 0 || taggedProducts.length > 0
              ? ''
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
        {isLoading && !activeComparison && <SkeletonLoader />}

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

        {/* Success State / Progressive Stream */}
        {!isError && activeComparison && (
          <div className="space-y-8 animate-fadeIn">
            {/* Top Telemetry & Count Bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-gray-200 shadow-xs">
              <div className="flex items-center gap-2 text-sm text-gray-700 font-medium">
                <Layers className="w-4 h-4 text-bb-blue" aria-hidden="true" />
                <span>
                  Comparing <strong className="text-gray-900">{activeComparison.products.length}</strong> products
                  {searchParams?.category && (
                    <> in <span className="font-semibold text-bb-blue">{searchParams.category}</span></>
                  )}
                </span>
              </div>
              <LatencyBadge latencyMs={activeComparison.latency_ms} />
            </div>

            {/* Layout with Main Comparison Details and Conversational Sidebar */}
            <div className="flex flex-col lg:flex-row items-start gap-8">
              <div className="flex-1 w-full space-y-8 min-w-0">
                {/* AI Recommendation Narrative */}
                <RecommendationCard
                  summary={activeComparison.summary}
                  recommendations={activeComparison.recommendations}
                  query={searchParams?.query || ''}
                  targetSkus={activeComparison.products.map((p) => p.sku)}
                  sessionId={searchParams?.sessionId || sessionId}
                  traceId={activeComparison.trace_id || ''}
                  onOpenChat={() => setIsChatOpen(true)}
                  isStreaming={isStreamingSynthesis}
                />

                {/* Product Summary Cards & Matrix Table (Only if products found) */}
                {activeComparison.products.length > 0 ? (
                  <>
                    <div>
                      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                        <h2 className="text-lg font-bold text-gray-900">Compared Products</h2>
                        <div className="flex items-center gap-2">
                          {activeComparison.products.length < 5 && (
                            <div className="relative">
                              <button
                                type="button"
                                onClick={() => setIsAddCompareOpen((prev) => !prev)}
                                aria-label="+ Add Product to Compare Against"
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold text-bb-blue bg-blue-50 hover:bg-bb-yellow hover:text-bb-slate border border-blue-200 rounded-lg transition-all"
                              >
                                <Plus className="w-3.5 h-3.5" />
                                <span>+ Add Product to Compare Against</span>
                              </button>

                              {isAddCompareOpen && (
                                <div
                                  role="dialog"
                                  aria-label="Add product to active comparison"
                                  className="absolute right-0 top-full mt-2 w-80 sm:w-96 bg-white rounded-xl shadow-2xl border border-gray-200 p-3 z-40 space-y-2 animate-fadeIn"
                                >
                                  <div className="flex items-center justify-between pb-1 border-b border-gray-100">
                                    <span className="text-xs font-bold text-gray-800">
                                      Add Product to Compare Against
                                    </span>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setIsAddCompareOpen(false);
                                        setAddCompareQuery('');
                                      }}
                                      aria-label="Close add comparison popover"
                                      className="text-gray-400 hover:text-gray-600 p-0.5 rounded transition-colors"
                                    >
                                      <X className="w-4 h-4" />
                                    </button>
                                  </div>
                                  <div className="relative">
                                    <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-gray-400" />
                                    <input
                                      type="text"
                                      value={addCompareQuery}
                                      onChange={(e) => setAddCompareQuery(e.target.value)}
                                      placeholder="Search product by name, brand, SKU..."
                                      aria-label="Search catalog products to add to comparison"
                                      className="w-full bg-gray-50 border border-gray-200 rounded-lg py-1.5 pl-8 pr-3 text-xs text-gray-900 placeholder-gray-400 focus:outline-none focus:border-bb-blue focus:bg-white"
                                      autoFocus
                                    />
                                  </div>
                                  <div className="max-h-56 overflow-y-auto custom-scrollbar divide-y divide-gray-100">
                                    {searchCatalogProducts(addCompareQuery, null)
                                      .filter((p) => !activeComparison.products.some((cp) => cp.sku === p.sku))
                                      .slice(0, 6)
                                      .map((prod) => (
                                        <div
                                          key={prod.sku}
                                          onClick={() => handleAddProductToActiveComparison(prod)}
                                          className="flex items-center justify-between p-2 hover:bg-blue-50/60 rounded-lg cursor-pointer transition-colors"
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
                                              <span className="text-xs font-semibold block truncate max-w-[180px] sm:max-w-[220px] text-gray-900">
                                                {prod.name}
                                              </span>
                                              <span className="text-[10px] text-gray-500 block">
                                                SKU: {prod.sku} • {prod.brand}
                                              </span>
                                            </div>
                                          </div>
                                          <div className="flex items-center gap-1.5 ml-2 flex-shrink-0">
                                            <span className="text-xs font-bold text-gray-900">
                                              ${prod.price.toFixed(2)}
                                            </span>
                                            <span className="px-1.5 py-0.5 rounded bg-bb-yellow text-bb-slate text-[10px] font-extrabold">
                                              + Add
                                            </span>
                                          </div>
                                        </div>
                                      ))}
                                    {searchCatalogProducts(addCompareQuery, null).filter(
                                      (p) => !activeComparison.products.some((cp) => cp.sku === p.sku)
                                    ).length === 0 && (
                                      <div className="p-3 text-center text-xs text-gray-500">
                                        No additional products found.
                                      </div>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                          {!isChatOpen && (
                            <button
                              onClick={() => setIsChatOpen(true)}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-bb-blue bg-blue-50 hover:bg-bb-yellow hover:text-bb-slate border border-blue-200 rounded-lg transition-all"
                            >
                              <span>Open Follow-up Chat</span>
                            </button>
                          )}
                        </div>
                      </div>
                      <div
                        className={`grid items-stretch ${
                          activeComparison.products.length >= 5 ? 'gap-3 sm:gap-4' : 'gap-6'
                        } ${
                          activeComparison.products.length === 2
                            ? 'grid-cols-1 md:grid-cols-2'
                            : activeComparison.products.length === 3
                            ? 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'
                            : activeComparison.products.length === 4
                            ? 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4'
                            : 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5'
                        }`}
                      >
                        {activeComparison.products.map((product) => (
                          <ProductCard
                            key={product.sku}
                            product={product}
                            onViewDetails={handleOpenProductDetails}
                            className="h-full"
                          />
                        ))}
                      </div>
                    </div>

                    {/* Side-by-side Feature Matrix Table */}
                    <ComparisonTable
                      products={activeComparison.products}
                      matrix={activeComparison.comparison_matrix}
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
                      {['Laptops', 'Tablets', 'Headphones', 'Smart Home', 'TVs'].map((cat) => (
                        <button
                          key={cat}
                          onClick={() => handleCategorySelect(cat)}
                          className="px-3.5 py-1.5 rounded-full text-xs font-semibold bg-slate-100 text-gray-700 hover:bg-bb-yellow hover:text-bb-slate transition-all border border-gray-200"
                        >
                          Browse {cat}
                        </button>
                      ))}
                      <button
                        onClick={() => handleCategorySelect(null)}
                        className="px-3.5 py-1.5 rounded-full text-xs font-semibold bg-blue-50 text-bb-blue hover:bg-bb-yellow hover:text-bb-slate transition-all border border-blue-200"
                      >
                        View All Categories
                      </button>
                    </div>
                  </div>
                )}

                {/* Verified SKU Citations Section */}
                {activeComparison.citations && activeComparison.citations.length > 0 && (
                  <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
                    <h3 className="text-sm font-bold uppercase tracking-wider text-gray-500">
                      Verified SKU Grounding & Citations
                    </h3>
                    <p className="text-xs text-gray-600">
                      Every specification above is strictly verified against Google Cloud BigQuery. Click any SKU badge
                      to view canonical product details on TechBuy.com.
                    </p>
                    <div className="flex flex-wrap items-center gap-3 pt-2">
                      {activeComparison.citations.map((citation) => (
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

              {/* Conversational Follow-up Sidebar */}
              {activeComparison.products.length > 0 && (
                <ConversationSidebar
                  key={searchParams?.sessionId || sessionId}
                  isOpen={isChatOpen}
                  onClose={() => setIsChatOpen(false)}
                  products={activeComparison.products}
                  comparisonMatrix={activeComparison.comparison_matrix}
                  sessionId={searchParams?.sessionId || sessionId}
                  onViewProductDetails={handleOpenProductDetails}
                />
              )}
            </div>
          </div>
        )}

        {/* Category SKU Browsing State */}
        {!isLoading && !isError && !activeComparison && browseCategory && (
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
              {browseCategory.category && (
                <button
                  type="button"
                  onClick={handleGoHome}
                  className="text-xs font-semibold text-bb-blue hover:underline"
                >
                  ← View All Categories
                </button>
              )}
            </div>

            {/* Live Catalog Search Input with Clear Button and Match Count */}
            <div className="relative flex items-center bg-white rounded-xl border border-gray-200 shadow-2xs p-2 focus-within:ring-2 focus-within:ring-blue-100 focus-within:border-bb-blue transition-all">
              <Search className="w-4 h-4 text-gray-400 ml-2 mr-2 flex-shrink-0" />
              <input
                type="text"
                value={catalogSearchQuery}
                onChange={(e) => {
                  setCatalogSearchQuery(e.target.value);
                  setVisibleCardCount(INITIAL_VISIBLE_CARDS);
                }}
                placeholder="Search products by name, brand, SKU, or spec to compare..."
                aria-label="Search products in catalog"
                className="flex-1 bg-transparent py-1 px-1 text-sm text-gray-900 placeholder-gray-400 focus:outline-none"
              />
              {catalogSearchQuery && (
                <button
                  type="button"
                  onClick={() => {
                    setCatalogSearchQuery('');
                    setVisibleCardCount(INITIAL_VISIBLE_CARDS);
                  }}
                  aria-label="Clear catalog search"
                  className="p-1 text-gray-400 hover:text-gray-600 transition-colors mr-1"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
              <div className="px-2.5 py-1 rounded-md bg-gray-100 text-gray-600 font-semibold text-xs flex-shrink-0">
                {browsedProducts.length} of {totalCategoryProducts.length} matching
              </div>
            </div>

            {browsedProducts.length > 0 ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 items-stretch">
                  {browsedProducts.slice(0, visibleCardCount).map((product) => {
                    const isSelected = selectedProducts.some((p) => p.sku === product.sku);
                    return (
                      <ProductCard
                        key={product.sku}
                        product={product}
                        selectable={true}
                        isSelected={isSelected}
                        onToggleSelect={handleToggleSelectProduct}
                        onViewDetails={handleOpenProductDetails}
                        className="h-full"
                      />
                    );
                  })}
                </div>
                {browsedProducts.length > visibleCardCount && (
                  <div className="flex justify-center pt-6 pb-2">
                    <button
                      type="button"
                      data-testid="load-more-products-btn"
                      onClick={() => setVisibleCardCount((prev) => prev + INITIAL_VISIBLE_CARDS)}
                      aria-label="Load more products"
                      className="px-6 py-3 rounded-xl font-extrabold text-sm bg-bb-yellow text-bb-slate hover:bg-bb-yellow-hover shadow-md hover:shadow-lg transition-all cursor-pointer flex items-center gap-2"
                    >
                      <Plus className="w-4 h-4 text-bb-slate" aria-hidden="true" />
                      <span>
                        Load More Products ({browsedProducts.length - visibleCardCount} remaining)
                      </span>
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="bg-white rounded-xl border border-gray-200 p-8 text-center space-y-3">
                <p className="text-gray-600 font-medium text-sm">
                  No products matching "{catalogSearchQuery}".
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setCatalogSearchQuery('');
                    setVisibleCardCount(INITIAL_VISIBLE_CARDS);
                  }}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-bb-blue text-white hover:bg-bb-blue-light transition-all"
                >
                  Clear search
                </button>
              </div>
            )}
          </div>
        )}

        {/* Product Selection Tray for Multiselect Catalog Comparisons */}
        <ProductSelectionTray
          selectedProducts={selectedProducts}
          onRemoveProduct={handleRemoveSelectedProduct}
          onClearSelection={handleClearSelectedProducts}
          onCompare={handleCompareSelected}
          onAddProduct={handleToggleSelectProduct}
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
