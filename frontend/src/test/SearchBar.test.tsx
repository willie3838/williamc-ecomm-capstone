import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SearchBar } from '../components/SearchBar';

describe('SearchBar', () => {
  it('renders input with default placeholder and search button', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    expect(screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /compare/i })).toBeInTheDocument();
  });

  it('renders category quick-filter pills', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={false} />);

    expect(screen.getByRole('button', { name: /all categories/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /laptops/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /tablets/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /headphones/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /smart home/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /tvs/i })).toBeInTheDocument();
  });

  it('submits query when search button is clicked', () => {
    const handleSearch = vi.fn();
    render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    const input = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(input, { target: { value: 'Compare iPad Pro vs Galaxy Tab' } });

    const submitBtn = screen.getByRole('button', { name: /compare/i });
    fireEvent.click(submitBtn);

    expect(handleSearch).toHaveBeenCalledTimes(1);
    expect(handleSearch).toHaveBeenCalledWith('Compare iPad Pro vs Galaxy Tab', null);
  });

  it('submits query with selected category filter', () => {
    const handleSearch = vi.fn();
    render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    // Select category pill
    fireEvent.click(screen.getByRole('button', { name: /tablets/i }));

    const input = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    fireEvent.change(input, { target: { value: 'Compare iPad Pro vs Galaxy Tab' } });

    fireEvent.submit(screen.getByRole('search'));

    expect(handleSearch).toHaveBeenCalledWith('Compare iPad Pro vs Galaxy Tab', 'Tablets');
  });

  it('disables submit button and input when isLoading is true', () => {
    render(<SearchBar onSearch={vi.fn()} isLoading={true} />);

    const input = screen.getByPlaceholderText(/compare macbook air m3 and dell xps 13/i);
    const submitBtn = screen.getByRole('button', { name: /comparing/i });

    expect(input).toBeDisabled();
    expect(submitBtn).toBeDisabled();
  });
});
