import React from 'react';
import { Database, Zap } from 'lucide-react';

export interface LatencyBadgeProps {
  latencyMs?: number | null;
  className?: string;
}

/**
 * Visual badge indicating execution latency and BigQuery grounding verification.
 */
export const LatencyBadge: React.FC<LatencyBadgeProps> = ({
  latencyMs,
  className = '',
}) => {
  if (latencyMs === undefined || latencyMs === null) {
    return null;
  }

  const formattedLatency =
    latencyMs >= 1000
      ? `${(latencyMs / 1000).toFixed(2)} s`
      : `${Math.round(latencyMs)} ms`;

  const isFast = latencyMs <= 3000;

  return (
    <div
      className={`inline-flex flex-wrap items-center gap-2 text-xs font-medium ${className}`}
      role="region"
      aria-label="Query execution telemetry"
    >
      {/* Latency chip */}
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border ${
          isFast
            ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
            : 'bg-amber-50 text-amber-800 border-amber-200'
        }`}
        title={`Total backend roundtrip latency: ${formattedLatency} (Target: ≤ 3.0s)`}
      >
        <Zap className="w-3 h-3 text-emerald-600" aria-hidden="true" />
        <span>{formattedLatency}</span>
      </span>

      {/* Grounding chip */}
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 border border-slate-200"
        title="All specifications verified against fde-bestbuy-sandbox-dev-508321.catalog.products"
      >
        <Database className="w-3 h-3 text-bb-blue" aria-hidden="true" />
        <span>Grounded in BigQuery</span>
      </span>
    </div>
  );
};
