import {
  CatalogResponse,
  ChatRequest,
  ChatResponse,
  ComparisonRequest,
  ComparisonResponse,
  ComparisonStreamCallbacks,
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
 * Streams product comparison using Server-Sent Events (SSE) over POST /api/compare/stream.
 * Yields progressive events (matrix_ready, synthesis_chunk, matrix_updated) via callbacks
 * and resolves to the final ComparisonResponse when complete.
 * Falls back to compareProducts(request) if SSE stream is unavailable or unsupported.
 *
 * @param request Comparison parameters including query, category, and top_k.
 * @param callbacks Optional callbacks for matrix_ready, synthesis_chunk, and matrix_updated events.
 * @returns Promise resolving to the complete ComparisonResponse.
 */
export async function compareProductsStream(
  request: ComparisonRequest,
  callbacks?: ComparisonStreamCallbacks
): Promise<ComparisonResponse> {
  const query = request.query?.trim();
  if (!query) {
    throw new Error('Query string must not be empty.');
  }

  const endpoint = `${API_BASE_URL}/api/compare/stream`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream, application/json',
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

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
  } catch (err) {
    console.warn('Streaming comparison failed to connect, falling back to standard comparison:', err);
    return compareProducts(request);
  }

  if (!response.ok) {
    if (response.status === 404 || response.status === 405) {
      return compareProducts(request);
    }
    let errorMessage = `Comparison stream failed with HTTP ${response.status}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorMessage = errorJson.detail;
      }
    } catch {
      if (response.statusText) {
        errorMessage = response.statusText;
      }
    }
    throw new Error(errorMessage);
  }

  if (!response.body || typeof response.body.getReader !== 'function') {
    try {
      const json = await response.json();
      return json as ComparisonResponse;
    } catch {
      return compareProducts(request);
    }
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalResponse: ComparisonResponse | null = null;

  let isDone = false;
  while (!isDone) {
    const { done, value } = await reader.read();
    if (done) {
      isDone = true;
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';

    for (const frame of frames) {
      const lines = frame.split('\n');
      let eventType = '';
      let dataStr = '';

      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventType = line.replace(/^event:\s*/, '').trim();
        } else if (line.startsWith('data:')) {
          dataStr = line.replace(/^data:\s*/, '').trim();
        }
      }

      if (!dataStr) continue;

      try {
        const payload = JSON.parse(dataStr);
        const resolvedEvent = payload.event || eventType;

        if (resolvedEvent === 'matrix_ready') {
          callbacks?.onMatrixReady?.({
            products: payload.products || [],
            comparison_matrix: payload.comparison_matrix || [],
            citations: payload.citations || [],
            session_id: payload.session_id,
            trace_id: payload.trace_id,
            timing_breakdown_ms: payload.timing_breakdown_ms,
          });
        } else if (resolvedEvent === 'synthesis_chunk') {
          callbacks?.onSynthesisChunk?.({
            summary: payload.summary || '',
            recommendations: payload.recommendations ?? null,
            delta: payload.delta,
          });
        } else if (resolvedEvent === 'matrix_updated') {
          callbacks?.onMatrixUpdated?.({
            comparison_matrix: payload.comparison_matrix || [],
            spec_winners: payload.spec_winners,
          });
        } else if (resolvedEvent === 'complete') {
          finalResponse = payload.data as ComparisonResponse;
        }
      } catch (err) {
        console.warn('Failed to parse SSE streaming frame:', err, dataStr);
      }
    }
  }

  if (finalResponse) {
    return finalResponse;
  }

  return compareProducts(request);
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

/**
 * Sends a conversational follow-up message grounded strictly in compared products.
 *
 * @param request Chat payload including message, conversation history, and compared products.
 * @returns Promise resolving to the grounded ChatResponse.
 */
export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  const message = request.message?.trim();
  if (!message) {
    throw new Error('Message string must not be empty.');
  }
  if (!request.products || request.products.length === 0) {
    throw new Error('At least one compared product must be provided for conversational grounding.');
  }

  const endpoint = `${API_BASE_URL}/api/chat`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (request.session_id) {
    headers['x-session-id'] = request.session_id;
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    let errorMessage = `Chat request failed with HTTP ${response.status}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorMessage = errorJson.detail;
      }
    } catch {
      if (response.statusText) {
        errorMessage = response.statusText;
      }
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

