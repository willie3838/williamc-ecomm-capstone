import React from 'react';
import { Sparkles, CheckCircle2 } from 'lucide-react';

export interface RecommendationCardProps {
  summary: string;
  recommendations?: string | null;
  className?: string;
}

/**
 * Narrative synthesis card displaying AI product comparison insights and recommendations.
 */
export const RecommendationCard: React.FC<RecommendationCardProps> = ({
  summary,
  recommendations,
  className = '',
}) => {
  return (
    <div
      className={`bg-white rounded-xl border border-blue-100 shadow-sm overflow-hidden p-6 transition-all ${className}`}
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-blue-50 rounded-lg text-bb-blue flex-shrink-0 mt-0.5">
          <Sparkles className="w-5 h-5 text-bb-blue" aria-hidden="true" />
        </div>
        <div className="flex-1 space-y-3">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider bg-yellow-100 text-yellow-900 border border-yellow-300 mb-1.5">
              AI Comparison Summary
            </div>
            <p className="text-gray-800 text-base leading-relaxed">{summary}</p>
          </div>

          {recommendations && (
            <div className="mt-4 pt-3 border-t border-gray-100">
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-1.5 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" aria-hidden="true" />
                Targeted Recommendation
              </h4>
              <p className="text-gray-700 text-sm leading-relaxed bg-slate-50 p-3 rounded-lg border border-slate-100">
                {recommendations}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
