import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from '../App';
import { mockComparisonResponse } from './mockData';

// Mock the client API
vi.mock('../api/client', () => ({
  compareProducts: vi.fn(),
  checkHealth: vi.fn(),
}));

import { compareProducts } from '../api/client';

const renderWithClient = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
};

describe('App Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders TechBuy Retailers branding, hero text, and sample comparisons by default', () => {
    renderWithClient(<App />);

    expect(screen.getByText('TECHBUY RETAILERS')).toBeInTheDocument();
    expect(
      screen.getByText('Compare Consumer Electronics Side-by-Side')
    ).toBeInTheDocument();
    expect(screen.getByText('MacBook Air M3 vs Dell XPS 13')).toBeInTheDocument();
    expect(
      screen.getByText('Sony WH-1000XM5 vs Bose QC Ultra')
    ).toBeInTheDocument();
  });

  it('executes search and displays comparison results, matrix, and citations', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    const searchInput = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(searchInput, {
      target: { value: 'Compare MacBook Air and Dell XPS 13' },
    });

    const compareBtn = screen.getByRole('button', { name: /^compare$/i });
    fireEvent.click(compareBtn);

    // Verify comparison response elements render
    await waitFor(() => {
      expect(screen.getByText(/The MacBook Air M3 offers unmatched battery life/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Side-by-Side Specification Matrix')).toBeInTheDocument();
    expect(screen.getByText('Compared Products')).toBeInTheDocument();
    expect(screen.getByText('Verified SKU Grounding & Citations')).toBeInTheDocument();
  });

  it('triggers comparison when a sample card is clicked', async () => {
    vi.mocked(compareProducts).mockResolvedValueOnce(mockComparisonResponse);

    renderWithClient(<App />);

    const sampleBtn = screen.getByText('MacBook Air M3 vs Dell XPS 13').closest('button');
    expect(sampleBtn).not.toBeNull();
    fireEvent.click(sampleBtn!);

    await waitFor(() => {
      expect(compareProducts).toHaveBeenCalledTimes(1);
    });
  });

  it('displays error state when comparison request fails', async () => {
    vi.mocked(compareProducts).mockRejectedValue(
      new Error('Catalog service temporarily unavailable')
    );

    renderWithClient(<App />);

    const searchInput = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(searchInput, {
      target: { value: 'Compare non-existent products' },
    });

    const compareBtn = screen.getByRole('button', { name: /^compare$/i });
    fireEvent.click(compareBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(screen.getByText('Comparison Failed')).toBeInTheDocument();
    expect(
      screen.getByText('Catalog service temporarily unavailable')
    ).toBeInTheDocument();
  });
});
