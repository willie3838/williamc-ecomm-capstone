import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RecommendationCard } from '../components/RecommendationCard';

describe('RecommendationCard', () => {
  it('renders summary narrative and AI badge', () => {
    render(
      <RecommendationCard
        summary="MacBook Air offers outstanding battery life."
        recommendations="Choose MacBook for battery endurance."
      />
    );

    expect(screen.getByText(/AI Comparison Summary/i)).toBeInTheDocument();
    expect(screen.getByText('MacBook Air offers outstanding battery life.')).toBeInTheDocument();
    expect(screen.getByText('Choose MacBook for battery endurance.')).toBeInTheDocument();
  });

  it('renders without optional recommendations gracefully', () => {
    render(<RecommendationCard summary="Only summary provided." />);
    expect(screen.getByText('Only summary provided.')).toBeInTheDocument();
    expect(screen.queryByText(/Recommendation/i)).not.toBeInTheDocument();
  });
});
