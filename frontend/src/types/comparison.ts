/**
 * Types mirroring backend FastAPI Pydantic schemas for the Best Buy Catalog Comparison Agent.
 */

export interface ProductSpec {
  sku: string;
  name: string;
  brand: string;
  category?: string | null;
  price: number;
  rating?: number | null;
  review_count?: number | null;
  specifications: Record<string, string | number | boolean | null>;
  url?: string | null;
  image_url?: string | null;
  in_stock: boolean;
}

// Backward compatibility alias
export type ProductItem = ProductSpec;

export interface MatrixRow {
  feature: string;
  values: Record<string, string | number | boolean | null>;
  winner_sku?: string | null;
}

export interface Citation {
  sku: string;
  url: string;
  description?: string | null;
}

export interface ComparisonResponse {
  summary: string;
  products: ProductSpec[];
  comparison_matrix: MatrixRow[];
  citations: Citation[];
  recommendations?: string | null;
  latency_ms?: number | null;
  session_id?: string | null;
  session_comparison_count?: number | null;
  trace_id?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  bq_bytes_billed?: number | null;
}

export interface ComparisonRequest {
  query: string;
  category?: string | null;
  top_k?: number;
  session_id?: string | null;
}

export interface UserActionPayload {
  action_type: 'compare_request' | 'copy_markdown' | 'category_filter' | 'sample_click' | 'sku_click';
  session_id: string;
  query?: string | null;
  category?: string | null;
  target_skus?: string[];
  metadata?: Record<string, unknown>;
}

export interface FeedbackPayload {
  rating: 'thumbs_up' | 'thumbs_down';
  session_id: string;
  query: string;
  target_skus?: string[];
  trace_id?: string | null;
  comment?: string | null;
}

export interface HealthResponse {
  status: string;
  service: string;
  project: string;
  version: string;
  environment: string;
}
