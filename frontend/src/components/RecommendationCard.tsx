import React, { useState } from 'react';
import { Sparkles, CheckCircle2, Award, Copy, Check, ThumbsUp, ThumbsDown } from 'lucide-react';
import { sendFeedback, sendUserAction } from '../api/client';

export interface RecommendationCardProps {
  summary: string;
  recommendations?: string | null;
  query?: string;
  targetSkus?: string[];
  sessionId?: string;
  traceId?: string;
  className?: string;
}

/**
 * Parses inline formatting like **bold text** and [SKU: 123456].
 */
const formatInlineText = (text: string): React.ReactNode => {
  const parts = text.split(/(\*\*[^*]+\*\*|\[SKU:\s*\d+\])/g);

  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={index} className="font-semibold text-gray-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('[SKU:') && part.endsWith(']')) {
      const sku = part.replace(/^\[SKU:\s*/, '').replace(/\]$/, '');
      return (
        <span
          key={index}
          className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono bg-blue-50 text-bb-blue border border-blue-200 mx-1 align-middle"
        >
          SKU: {sku}
        </span>
      );
    }
    return part;
  });
};

/**
 * Formats a block of text into structured paragraphs and bullet list items.
 */
const renderStructuredContent = (rawText: string) => {
  if (!rawText) return null;

  const lines = rawText
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);

  const introParagraphs: string[] = [];
  const bulletItems: string[] = [];

  lines.forEach((line) => {
    if (line.startsWith('- ') || line.startsWith('* ')) {
      bulletItems.push(line.replace(/^[-*]\s*/, ''));
    } else {
      introParagraphs.push(line);
    }
  });

  return (
    <div className="space-y-3">
      {introParagraphs.map((para, idx) => (
        <p key={idx} className="text-gray-800 text-sm md:text-base leading-relaxed">
          {formatInlineText(para)}
        </p>
      ))}

      {bulletItems.length > 0 && (
        <ul className="space-y-2.5 pt-1">
          {bulletItems.map((bullet, idx) => {
            const colonIndex = bullet.indexOf(':');
            let categoryTag: string | null = null;
            let bodyText = bullet;

            if (colonIndex > 0 && colonIndex < 35) {
              categoryTag = bullet.slice(0, colonIndex).trim();
              bodyText = bullet.slice(colonIndex + 1).trim();
            }

            return (
              <li
                key={idx}
                className="flex items-start gap-2.5 text-sm text-gray-700 bg-slate-50/90 rounded-lg p-2.5 border border-slate-200/70"
              >
                {categoryTag ? (
                  <>
                    <span className="font-bold text-bb-blue bg-blue-50 border border-blue-100 px-2 py-0.5 rounded text-xs uppercase tracking-wide shrink-0 mt-0.5">
                      {categoryTag}
                    </span>
                    <span className="leading-relaxed">{formatInlineText(bodyText)}</span>
                  </>
                ) : (
                  <>
                    <Award className="w-4 h-4 text-bb-blue shrink-0 mt-0.5" aria-hidden="true" />
                    <span className="leading-relaxed">{formatInlineText(bodyText)}</span>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

/**
 * Narrative synthesis card displaying AI product comparison insights, recommendations,
 * Copy Markdown action, and Thumbs-up / Thumbs-down feedback.
 */
export const RecommendationCard: React.FC<RecommendationCardProps> = ({
  summary,
  recommendations,
  query = '',
  targetSkus = [],
  sessionId = '',
  traceId = '',
  className = '',
}) => {
  const [copied, setCopied] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState<'thumbs_up' | 'thumbs_down' | null>(null);

  const handleCopyMarkdown = async () => {
    let markdown = `## Product Comparison Summary\n\n${summary}\n`;
    if (recommendations) {
      markdown += `\n### Buying Recommendations\n\n${recommendations}\n`;
    }

    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn('Failed to copy to clipboard:', err);
    }

    if (sessionId) {
      sendUserAction({
        action_type: 'copy_markdown',
        session_id: sessionId,
        query,
        target_skus: targetSkus,
      });
    }
  };

  const handleFeedback = (rating: 'thumbs_up' | 'thumbs_down') => {
    setFeedbackRating(rating);
    if (sessionId) {
      sendFeedback({
        rating,
        session_id: sessionId,
        query,
        target_skus: targetSkus,
        trace_id: traceId || null,
      });
    }
  };

  return (
    <div
      className={`bg-white rounded-xl border border-blue-100 shadow-sm overflow-hidden p-6 transition-all ${className}`}
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-blue-50 rounded-lg text-bb-blue flex-shrink-0 mt-0.5">
          <Sparkles className="w-5 h-5 text-bb-blue" aria-hidden="true" />
        </div>
        <div className="flex-1 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider bg-yellow-100 text-yellow-900 border border-yellow-300">
              AI Comparison Summary
            </div>

            {/* User Actions & Feedback Toolbar */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleCopyMarkdown}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-gray-700 bg-slate-50 hover:bg-slate-100 border border-gray-200 rounded-lg transition-colors cursor-pointer"
                title="Copy markdown summary to clipboard"
                aria-label="Copy comparison as markdown"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-600" aria-hidden="true" />
                    <span className="text-emerald-700 font-semibold">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5 text-gray-500" aria-hidden="true" />
                    <span>Copy Markdown</span>
                  </>
                )}
              </button>

              <div className="flex items-center border border-gray-200 rounded-lg overflow-hidden bg-slate-50">
                <button
                  onClick={() => handleFeedback('thumbs_up')}
                  className={`p-1.5 transition-colors ${
                    feedbackRating === 'thumbs_up'
                      ? 'bg-blue-100 text-bb-blue'
                      : 'text-gray-500 hover:text-bb-blue hover:bg-slate-100'
                  }`}
                  title="Helpful comparison (thumbs up)"
                  aria-label="Thumbs up"
                >
                  <ThumbsUp className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
                <button
                  onClick={() => handleFeedback('thumbs_down')}
                  className={`p-1.5 transition-colors border-l border-gray-200 ${
                    feedbackRating === 'thumbs_down'
                      ? 'bg-red-100 text-red-600'
                      : 'text-gray-500 hover:text-red-600 hover:bg-slate-100'
                  }`}
                  title="Not helpful comparison (thumbs down)"
                  aria-label="Thumbs down"
                >
                  <ThumbsDown className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              </div>
            </div>
          </div>

          {renderStructuredContent(summary)}

          {recommendations && (
            <div className="mt-4 pt-4 border-t border-gray-100">
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-2 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" aria-hidden="true" />
                Targeted Recommendation
              </h4>
              <div className="bg-slate-50/80 p-3.5 rounded-lg border border-slate-100">
                {renderStructuredContent(recommendations)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
