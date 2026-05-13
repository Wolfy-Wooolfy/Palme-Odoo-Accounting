import { useState, useRef, useEffect } from 'react';
import { Sparkles, Bot } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useFilters } from '../context/FilterContext';
import { useChatStatus, useChatMutation } from '../hooks/useChat';
import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';
import ErrorBanner from '../components/ErrorBanner';

const SUGGESTED_KEYS = [
  'chat.suggest_1',
  'chat.suggest_2',
  'chat.suggest_3',
  'chat.suggest_4',
];

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 h-8 w-8 rounded-full bg-violet-600 flex items-center justify-center">
        <Bot className="h-4 w-4 text-white" />
      </div>
      <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3">
        <div className="flex gap-1 items-center h-4">
          <span className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:0ms]" />
          <span className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:150ms]" />
          <span className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}

function WelcomeScreen({ onSuggest, t }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-6 py-12 px-4">
      <div className="bg-violet-100 rounded-2xl p-4">
        <Sparkles className="h-8 w-8 text-violet-600" />
      </div>
      <div className="text-center max-w-sm">
        <h2 className="text-lg font-semibold text-slate-800 mb-1">{t('chat.welcome_title')}</h2>
        <p className="text-sm text-slate-500">{t('chat.welcome_subtitle')}</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
        {SUGGESTED_KEYS.map((key) => (
          <button
            key={key}
            onClick={() => onSuggest(t(key))}
            className="text-start text-sm bg-white border border-slate-200 hover:border-violet-300 hover:bg-violet-50 text-slate-600 hover:text-violet-700 rounded-xl px-4 py-3 transition-colors"
          >
            {t(key)}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function AIChat() {
  const { t } = useTranslation();
  const { filters } = useFilters();
  const { data: status, isLoading: statusLoading } = useChatStatus();
  const mutation = useChatMutation();
  const [messages, setMessages] = useState([]);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, mutation.isPending]);

  const handleSend = (text) => {
    const userMsg = { role: 'user', content: text, tool_calls: [] };
    const nextHistory = [...messages, userMsg];
    setMessages(nextHistory);

    mutation.mutate(
      {
        message: text,
        history: messages.map((m) => ({ role: m.role, content: m.content })),
        date_from: filters.date_from,
        date_to: filters.date_to,
        company_id: filters.company_id ?? null,
      },
      {
        onSuccess: (data) => {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: data.reply, tool_calls: data.tool_calls ?? [] },
          ]);
        },
        onError: () => {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: t('chat.error_reply'), tool_calls: [] },
          ]);
        },
      },
    );
  };

  if (statusLoading) return null;

  if (!status?.available) {
    return (
      <div className="max-w-2xl mx-auto py-12 px-4">
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
          <Sparkles className="h-8 w-8 text-amber-500 mx-auto mb-3" />
          <h2 className="font-semibold text-amber-900 mb-1">{t('chat.not_configured_title')}</h2>
          <p className="text-sm text-amber-700">{t('chat.not_configured_body')}</p>
          <code className="mt-3 block text-xs bg-amber-100 rounded-lg px-3 py-2 font-mono text-amber-800">
            OPENAI_API_KEY=sk-...
          </code>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] bg-slate-50 rounded-xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="bg-violet-100 rounded-xl p-2">
          <Sparkles className="h-5 w-5 text-violet-600" />
        </div>
        <div>
          <h1 className="text-sm font-semibold text-slate-900">{t('chat.title')}</h1>
          <p className="text-xs text-slate-500">{t('chat.subtitle', { model: status.model })}</p>
        </div>
        <span className="ms-auto text-xs bg-violet-100 text-violet-700 rounded-full px-2.5 py-0.5 font-medium">
          {t('safety.badge')}
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 ? (
          <WelcomeScreen onSuggest={handleSend} t={t} />
        ) : (
          <>
            {messages.map((msg, i) => (
              <ChatMessage key={i} message={msg} />
            ))}
            {mutation.isPending && <TypingIndicator />}
            {mutation.isError && <ErrorBanner error={mutation.error} />}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} loading={mutation.isPending} />
    </div>
  );
}
