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

  it('renders structured bullet points with category tags and bold formatting', () => {
    const markdownSummary = `Direct comparison between two laptops:
- Price: Apple MacBook Air is **$100 more affordable** at $1,099.
- Battery Life: Apple leads with up to **18 hours**.`;

    render(<RecommendationCard summary={markdownSummary} />);

    expect(screen.getByText('Price')).toBeInTheDocument();
    expect(screen.getByText('Battery Life')).toBeInTheDocument();
    expect(screen.getByText('$100 more affordable')).toHaveClass('font-semibold');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('renders Copy Markdown button and Thumbs Up/Down feedback controls', async () => {
    const { fireEvent } = await import('@testing-library/react');
    const { vi } = await import('vitest');

    // Mock clipboard API
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });

    render(
      <RecommendationCard
        summary="Test comparison summary."
        recommendations="Test recommendation."
        sessionId="sess-test-123"
        query="Compare laptops"
        targetSkus={['11111', '22222']}
      />
    );

    const copyBtn = screen.getByRole('button', { name: /copy comparison as markdown/i });
    expect(copyBtn).toBeInTheDocument();
    fireEvent.click(copyBtn);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('## Product Comparison Summary')
    );

    const thumbsUpBtn = screen.getByRole('button', { name: /thumbs up/i });
    const thumbsDownBtn = screen.getByRole('button', { name: /thumbs down/i });
    expect(thumbsUpBtn).toBeInTheDocument();
    expect(thumbsDownBtn).toBeInTheDocument();

    fireEvent.click(thumbsUpBtn);
    expect(thumbsUpBtn).toHaveClass('bg-blue-100');
  });
});
