import React, { useState, useRef, useEffect } from 'react';
import {
  MessageSquare,
  Send,
  X,
  Sparkles,
  Bot,
  User,
  HelpCircle,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { ChatMessage, MatrixRow, ProductSpec } from '../types/comparison';
import { sendChatMessage } from '../api/client';
import { CitationChip } from './CitationChip';

export interface ConversationSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  products: ProductSpec[];
  comparisonMatrix?: MatrixRow[];
  sessionId?: string;
  onViewProductDetails?: (productOrSku: ProductSpec | string) => void;
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
  isOpen,
  onClose,
  products,
  comparisonMatrix,
  sessionId,
  onViewProductDetails,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([
    'Which option has the longest battery life?',
    'Which product is better value for money?',
    'How do their processors and performance compare?',
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen]);

  const handleSend = async (messageText?: string) => {
    const textToSend = (messageText ?? inputValue).trim();
    if (!textToSend || isLoading) return;

    setError(null);
    const userMsg: ChatMessage = { role: 'user', content: textToSend };
    const nextHistory = [...messages, userMsg];
    setMessages(nextHistory);
    if (!messageText) {
      setInputValue('');
    }
    setIsLoading(true);

    try {
      const response = await sendChatMessage({
        message: textToSend,
        conversation_history: nextHistory,
        products,
        comparison_matrix: comparisonMatrix,
        session_id: sessionId,
      });

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: response.reply,
      };
      setMessages([...nextHistory, assistantMsg]);

      if (response.suggested_followups && response.suggested_followups.length > 0) {
        setSuggestedQuestions(response.suggested_followups);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to send message';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const renderMessageContent = (content: string) => {
    // Regex splits on [SKU: 1234567]
    const parts = content.split(/(\[SKU:\s*\d+\])/g);
    return parts.map((part, idx) => {
      if (part.startsWith('[SKU:') && part.endsWith(']')) {
        const sku = part.replace(/^\[SKU:\s*/, '').replace(/\]$/, '');
        return (
          <CitationChip
            key={idx}
            sku={sku}
            url={`https://www.techbuy.com/site/sku/${sku}.p`}
            onClick={() => onViewProductDetails?.(sku)}
            className="inline-flex mx-1"
          />
        );
      }
      return <span key={idx}>{part}</span>;
    });
  };

  if (!isOpen) return null;

  return (
    <aside
      aria-label="Follow-up Conversation Sidebar"
      className="w-full lg:w-96 flex flex-col bg-white border border-gray-200 rounded-2xl shadow-lg h-[650px] lg:h-[750px] sticky top-24 z-20 overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3.5 bg-gradient-to-r from-bb-slate to-slate-900 text-white">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-bb-blue/30 rounded-lg text-bb-yellow">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
              Comparison Assistant
              <span className="text-[10px] uppercase font-semibold bg-bb-blue text-white px-1.5 py-0.2 rounded-full">
                AI
              </span>
            </h3>
            <p className="text-[11px] text-gray-300">
              Grounded strictly in {products.length} compared products
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Close conversation sidebar"
          className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Messages Stream */}
      <div className="flex-1 p-4 overflow-y-auto space-y-4 bg-slate-50/60">
        {messages.length === 0 ? (
          <div className="text-center py-6 px-3 space-y-3">
            <div className="w-10 h-10 rounded-full bg-blue-50 text-bb-blue flex items-center justify-center mx-auto">
              <MessageSquare className="w-5 h-5" />
            </div>
            <h4 className="text-sm font-semibold text-gray-900">
              Ask about these products
            </h4>
            <p className="text-xs text-gray-500 max-w-xs mx-auto">
              Ask follow-up questions about specifications, trade-offs, battery life, or value.
              All answers cite verified SKUs from Google Cloud BigQuery.
            </p>
          </div>
        ) : (
          messages.map((msg, index) => {
            const isUser = msg.role === 'user';
            return (
              <div
                key={index}
                className={`flex items-start gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
              >
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold ${
                    isUser ? 'bg-bb-blue text-white' : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>
                <div
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-xs md:text-sm leading-relaxed ${
                    isUser
                      ? 'bg-bb-blue text-white rounded-tr-none'
                      : 'bg-white text-gray-900 border border-gray-200 rounded-tl-none shadow-2xs'
                  }`}
                >
                  {isUser ? msg.content : renderMessageContent(msg.content)}
                </div>
              </div>
            );
          })
        )}

        {isLoading && (
          <div className="flex items-start gap-2.5">
            <div className="w-7 h-7 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center shrink-0">
              <Bot className="w-4 h-4" />
            </div>
            <div className="bg-white text-gray-500 border border-gray-200 rounded-2xl rounded-tl-none px-3.5 py-2.5 text-xs flex items-center gap-2 shadow-2xs">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-bb-blue" />
              <span>Analyzing catalog specs...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-xl text-xs flex items-center justify-between">
            <span>{error}</span>
            <button
              onClick={() => handleSend()}
              className="text-red-700 font-semibold hover:underline flex items-center gap-1"
            >
              <RefreshCw className="w-3 h-3" /> Retry
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Follow-up Questions */}
      {suggestedQuestions.length > 0 && (
        <div className="px-3 py-2 bg-white border-t border-gray-100">
          <div className="flex items-center gap-1 text-[11px] font-semibold text-gray-500 mb-1.5">
            <HelpCircle className="w-3 h-3 text-bb-blue" />
            <span>Suggested follow-ups:</span>
          </div>
          <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
            {suggestedQuestions.map((q, idx) => (
              <button
                key={idx}
                disabled={isLoading}
                onClick={() => handleSend(q)}
                className="text-left text-[11px] bg-slate-100 hover:bg-bb-yellow hover:text-bb-slate transition-all text-gray-700 px-2.5 py-1 rounded-full border border-gray-200 disabled:opacity-50"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Form */}
      <div className="p-3 bg-white border-t border-gray-200">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder="Ask a follow-up question..."
            className="flex-1 text-xs md:text-sm px-3.5 py-2 border border-gray-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-bb-blue focus:border-transparent disabled:bg-gray-100"
          />
          <button
            type="submit"
            disabled={!inputValue.trim() || isLoading}
            aria-label="Send follow-up question"
            className="p-2 bg-bb-blue text-white rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:hover:bg-bb-blue shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </aside>
  );
};
