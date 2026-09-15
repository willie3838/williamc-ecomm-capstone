import {
  ComparisonRequest,
  ComparisonResponse,
  HealthResponse,
} from '../types/comparison';

const API_BASE_URL =
  import.meta.env?.VITE_API_BASE_URL || '';

/**
 * Initiates an agentic product comparison grounded in Google Cloud BigQuery.
 *
 * @param request Comparison parameters including query, category, and top_k.
 * @returns Promise resolving to the complete ComparisonResponse.
 */
export async function compareProducts(
  request: ComparisonRequest
): Promise<ComparisonResponse> {
  const query = request.query?.trim();
  if (!query) {
    throw new Error('Query string must not be empty.');
  }

  const endpoint = `${API_BASE_URL}/api/compare`;

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      query,
      category: request.category || null,
      top_k: request.top_k || 5,
    }),
  });

  if (!response.ok) {
    let errorMessage = `Comparison request failed with HTTP ${response.status}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorMessage = errorJson.detail;
      }
    } catch {
      // Fallback to generic status text if non-JSON body
      if (response.statusText) {
        errorMessage = response.statusText;
      }
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

/**
 * Liveness and readiness health probe client.
 */
export async function checkHealth(): Promise<HealthResponse> {
  const endpoint = `${API_BASE_URL}/health`;
  const response = await fetch(endpoint, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Health check failed with HTTP ${response.status}`);
  }

  return response.json();
}
