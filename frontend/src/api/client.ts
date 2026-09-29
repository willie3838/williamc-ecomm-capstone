import {
  CatalogResponse,
  ComparisonRequest,
  ComparisonResponse,
  HealthResponse,
  ProductSpec,
} from '../types/comparison';
import { getCatalogProducts } from '../data/catalogProducts';

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

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (request.session_id) {
    headers['x-session-id'] = request.session_id;
  }

  const payload: Record<string, unknown> = {
    query,
    category: request.category || null,
    top_k: request.top_k || 5,
  };
  if (request.session_id) {
    payload.session_id = request.session_id;
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
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
 * Log user action (e.g. copy markdown, filter selection) to Firestore.
 */
export async function sendUserAction(payload: import('../types/comparison').UserActionPayload): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/actions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    console.warn('Failed to dispatch user action:', err);
  }
}

/**
 * Submit thumbs-up / thumbs-down evaluation feedback to Firestore.
 */
export async function sendFeedback(payload: import('../types/comparison').FeedbackPayload): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/feedback`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    console.warn('Failed to dispatch user feedback:', err);
  }
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

/**
 * Retrieves verified catalog products from backend /api/catalog endpoint with graceful client fallback.
 *
 * @param category Optional product taxonomy category to filter (e.g. 'Laptops', 'Tablets').
 * @returns Promise resolving to list of grounded ProductSpec records.
 */
export async function fetchCatalog(category?: string | null): Promise<ProductSpec[]> {
  const queryParam = category ? `?category=${encodeURIComponent(category)}` : '';
  const endpoint = `${API_BASE_URL}/api/catalog${queryParam}`;

  try {
    const response = await fetch(endpoint, {
      headers: { Accept: 'application/json' },
    });

    if (response.ok) {
      const data: CatalogResponse = await response.json();
      if (Array.isArray(data.products) && data.products.length > 0) {
        return data.products;
      }
    }
  } catch (err) {
    console.warn('Backend /api/catalog request failed, falling back to local catalog data:', err);
  }

  // Graceful fallback to verified client catalog dataset
  return getCatalogProducts(category);
}

