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
});
