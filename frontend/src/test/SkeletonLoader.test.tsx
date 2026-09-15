import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { SkeletonLoader } from '../components/SkeletonLoader';

describe('SkeletonLoader', () => {
  it('renders loading state with accessible aria-busy attribute', () => {
    render(<SkeletonLoader />);
    const container = screen.getByRole('status');
    expect(container).toBeInTheDocument();
    expect(container).toHaveAttribute('aria-busy', 'true');
  });

  it('renders shimmer skeleton elements for products and matrix rows', () => {
    const { container } = render(<SkeletonLoader />);
    const pulseElements = container.querySelectorAll('.animate-pulse');
    expect(pulseElements.length).toBeGreaterThan(0);
  });
});
