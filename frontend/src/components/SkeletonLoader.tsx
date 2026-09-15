import React from 'react';

export interface SkeletonLoaderProps {
  className?: string;
}

/**
 * High-fidelity shimmer skeleton loader displayed during query synthesis.
 * Provides immediate feedback within <100ms.
 */
export const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({ className = '' }) => {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading comparison data from BigQuery catalog"
      className={`space-y-6 animate-pulse ${className}`}
    >
      {/* AI Summary Recommendation Skeleton */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
        <div className="h-4 w-32 bg-blue-100 rounded"></div>
        <div className="space-y-2">
          <div className="h-4 w-full bg-gray-200 rounded"></div>
          <div className="h-4 w-5/6 bg-gray-200 rounded"></div>
          <div className="h-4 w-3/4 bg-gray-200 rounded"></div>
        </div>
      </div>

      {/* Product Cards Skeleton Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {[1, 2].map((idx) => (
          <div
            key={idx}
            className="bg-white rounded-xl border border-gray-200 p-4 space-y-3 flex flex-col"
          >
            <div className="h-44 w-full bg-gray-200 rounded-lg"></div>
            <div className="h-3 w-16 bg-blue-100 rounded"></div>
            <div className="h-4 w-full bg-gray-200 rounded"></div>
            <div className="h-4 w-2/3 bg-gray-200 rounded"></div>
            <div className="pt-4 border-t border-gray-100 flex items-center justify-between">
              <div className="h-6 w-20 bg-gray-300 rounded"></div>
              <div className="h-8 w-28 bg-yellow-100 rounded"></div>
            </div>
          </div>
        ))}
      </div>

      {/* Comparison Matrix Table Skeleton */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="p-4 border-b border-gray-100">
          <div className="h-5 w-48 bg-gray-200 rounded"></div>
        </div>
        <div className="divide-y divide-gray-100">
          {[1, 2, 3, 4, 5].map((rowIdx) => (
            <div key={rowIdx} className="grid grid-cols-3 p-4 gap-4">
              <div className="h-4 w-24 bg-gray-200 rounded"></div>
              <div className="h-4 w-36 bg-gray-100 rounded"></div>
              <div className="h-4 w-36 bg-gray-100 rounded"></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
