import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { LatencyBadge } from '../components/LatencyBadge';

describe('LatencyBadge', () => {
  it('formats latency in milliseconds when < 1000ms', () => {
    render(<LatencyBadge latencyMs={450.2} />);
    expect(screen.getByText(/450 ms/i)).toBeInTheDocument();
  });

  it('formats latency in seconds when >= 1000ms', () => {
    render(<LatencyBadge latencyMs={1850.5} />);
    expect(screen.getByText(/1.85 s/i)).toBeInTheDocument();
  });

  it('displays BigQuery grounding badge and GCP target indicator', () => {
    render(<LatencyBadge latencyMs={1200} />);
    expect(screen.getByText(/Grounded in BigQuery/i)).toBeInTheDocument();
  });

  it('renders nothing when latencyMs is undefined or null', () => {
    const { container } = render(<LatencyBadge />);
    expect(container.firstChild).toBeNull();
  });
});
