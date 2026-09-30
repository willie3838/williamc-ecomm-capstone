import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConversationSidebar } from '../components/ConversationSidebar';
import { mockMacBook, mockDellXPS } from './mockData';
import * as clientModule from '../api/client';

describe('ConversationSidebar Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <ConversationSidebar
        isOpen={false}
        onClose={vi.fn()}
        products={[mockMacBook, mockDellXPS]}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders header, product count, empty chat prompt, and input when open', () => {
    render(
      <ConversationSidebar
        isOpen={true}
        onClose={vi.fn()}
        products={[mockMacBook, mockDellXPS]}
      />
    );

    expect(screen.getByText('Comparison Assistant')).toBeInTheDocument();
    expect(screen.getByText(/Grounded strictly in 2 compared products/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Ask a follow-up question...')).toBeInTheDocument();
    expect(screen.getByText('Ask about these products')).toBeInTheDocument();
    expect(screen.getByText('Which option has the longest battery life?')).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <ConversationSidebar
        isOpen={true}
        onClose={onClose}
        products={[mockMacBook, mockDellXPS]}
      />
    );

    const closeBtn = screen.getByLabelText('Close conversation sidebar');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('sends user message and displays assistant response with citations', async () => {
    const sendChatSpy = vi.spyOn(clientModule, 'sendChatMessage').mockResolvedValueOnce({
      reply: 'The MacBook Air M3 [SKU: 6534606] has 18 hours battery life.',
      citations: [
        {
          sku: '6534606',
          url: 'https://www.techbuy.com/site/sku/6534606.p',
        },
      ],
      suggested_followups: ['How much does the Dell weigh?', 'Which has more RAM?'],
      latency_ms: 120,
    });

    render(
      <ConversationSidebar
        isOpen={true}
        onClose={vi.fn()}
        products={[mockMacBook, mockDellXPS]}
        sessionId="test-session"
      />
    );

    const input = screen.getByPlaceholderText('Ask a follow-up question...');
    fireEvent.change(input, { target: { value: 'Which has better battery?' } });

    const submitBtn = screen.getByLabelText('Send follow-up question');
    fireEvent.click(submitBtn);

    // Assert user message is rendered immediately
    expect(screen.getByText('Which has better battery?')).toBeInTheDocument();

    // Await assistant reply
    await waitFor(() => {
      expect(screen.getByText(/has 18 hours battery life/i)).toBeInTheDocument();
    });

    expect(sendChatSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'Which has better battery?',
        products: [mockMacBook, mockDellXPS],
        session_id: 'test-session',
      })
    );

    // Verify suggested follow-ups updated
    expect(screen.getByText('How much does the Dell weigh?')).toBeInTheDocument();
  });

  it('clicking a suggested question submits it', async () => {
    const sendChatSpy = vi.spyOn(clientModule, 'sendChatMessage').mockResolvedValueOnce({
      reply: 'MacBook Air has 18h battery [SKU: 6534606].',
      citations: [],
      suggested_followups: [],
    });

    render(
      <ConversationSidebar
        isOpen={true}
        onClose={vi.fn()}
        products={[mockMacBook, mockDellXPS]}
      />
    );

    const suggestedBtn = screen.getByText('Which option has the longest battery life?');
    fireEvent.click(suggestedBtn);

    await waitFor(() => {
      expect(screen.getAllByText('Which option has the longest battery life?').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/MacBook Air has 18h battery/i)).toBeInTheDocument();
    });

    expect(sendChatSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'Which option has the longest battery life?',
      })
    );
  });

  it('handles and displays error message with retry button', async () => {
    vi.spyOn(clientModule, 'sendChatMessage').mockRejectedValueOnce(
      new Error('Network timeout talking to chat service')
    );

    render(
      <ConversationSidebar
        isOpen={true}
        onClose={vi.fn()}
        products={[mockMacBook, mockDellXPS]}
      />
    );

    const input = screen.getByPlaceholderText('Ask a follow-up question...');
    fireEvent.change(input, { target: { value: 'Does it support HDMI?' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(screen.getByText('Network timeout talking to chat service')).toBeInTheDocument();
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });
  });

  it('triggers onViewProductDetails when citation chip in reply is clicked', async () => {
    vi.spyOn(clientModule, 'sendChatMessage').mockResolvedValueOnce({
      reply: 'Check out the Dell [SKU: 6573822].',
      citations: [],
      suggested_followups: [],
    });

    const onViewDetails = vi.fn();

    render(
      <ConversationSidebar
        isOpen={true}
        onClose={vi.fn()}
        products={[mockMacBook, mockDellXPS]}
        onViewProductDetails={onViewDetails}
      />
    );

    const input = screen.getByPlaceholderText('Ask a follow-up question...');
    fireEvent.change(input, { target: { value: 'Show Dell SKU' } });
    fireEvent.submit(input.closest('form')!);

    const citationBtn = await screen.findByRole('button', {
      name: /View product details for SKU 6573822/i,
    });
    expect(citationBtn).toBeInTheDocument();

    fireEvent.click(citationBtn);
    expect(onViewDetails).toHaveBeenCalledWith('6573822');
  });
});
