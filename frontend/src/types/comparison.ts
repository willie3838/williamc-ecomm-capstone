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
}

export interface ComparisonRequest {
  query: string;
  category?: string | null;
  top_k?: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  project: string;
  version: string;
  environment: string;
}
