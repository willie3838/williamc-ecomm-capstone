import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { compareProducts } from '../api/client';
import { mockComparisonResponse } from './mockData';

describe('API client: compareProducts', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('posts comparison request and parses successful response', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => mockComparisonResponse,
    });

    const result = await compareProducts({
      query: 'Compare MacBook and Dell',
      category: 'Laptops',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/compare');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body as string)).toEqual({
      query: 'Compare MacBook and Dell',
      category: 'Laptops',
      top_k: 5,
    });
    expect(result).toEqual(mockComparisonResponse);
  });

  it('throws informative error on non-ok HTTP response', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Query string must not be empty.' }),
    });

    await expect(
      compareProducts({ query: '   ' })
    ).rejects.toThrow('Query string must not be empty.');
  });

  it('handles network failure gracefully', async () => {
    fetchMock.mockRejectedValueOnce(new Error('Failed to fetch'));

    await expect(
      compareProducts({ query: 'Compare laptops' })
    ).rejects.toThrow('Failed to fetch');
  });

  it('falls back to statusText on non-JSON error responses', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      json: async () => {
        throw new Error('Not JSON');
      },
    });

    await expect(
      compareProducts({ query: 'Compare laptops' })
    ).rejects.toThrow('Bad Gateway');
  });

  it('calls /health and parses HealthResponse', async () => {
    const mockHealth = {
      status: 'ok',
      service: 'catalog-backend',
      project: 'fde-bestbuy-sandbox-dev-508321',
      version: '0.1.0',
      environment: 'development',
    };
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => mockHealth,
    });

    const { checkHealth } = await import('../api/client');
    const health = await checkHealth();
    expect(health).toEqual(mockHealth);
  });

  it('throws error when /health returns non-ok status', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 503,
    });

    const { checkHealth } = await import('../api/client');
    await expect(checkHealth()).rejects.toThrow('Health check failed with HTTP 503');
  });

  it('fetchCatalog returns products from /api/catalog on successful response', async () => {
    const mockCatalogResp = {
      products: [
        {
          sku: '6534606',
          name: 'Apple MacBook Air M3',
          brand: 'Apple',
          category: 'Laptops',
          price: 1099.0,
          specifications: { ram_gb: 16 },
          in_stock: true,
        },
      ],
      total_count: 1,
      category: 'Laptops',
    };
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => mockCatalogResp,
    });

    const { fetchCatalog } = await import('../api/client');
    const products = await fetchCatalog('Laptops');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/catalog?category=Laptops');
    expect(products).toHaveLength(1);
    expect(products[0].sku).toBe('6534606');
  });

  it('fetchCatalog gracefully falls back to local catalog data if network request fails', async () => {
    fetchMock.mockRejectedValueOnce(new Error('Network error'));

    const { fetchCatalog } = await import('../api/client');
    const products = await fetchCatalog('Laptops');
    expect(products.length).toBeGreaterThan(0);
    expect(products[0].category).toBe('Laptops');
  });
});

