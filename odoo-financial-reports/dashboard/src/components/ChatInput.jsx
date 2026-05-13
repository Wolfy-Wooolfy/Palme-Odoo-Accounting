import { useRef, useEffect } from 'react';
import { Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';

export default function ChatInput({ onSend, loading }) {
  const { t } = useTranslation();
  const ref = useRef(null);

  useEffect(() => {
    if (!loading && ref.current) ref.current.focus();
  }, [loading]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const submit = () => {
    const value = ref.current?.value?.trim();
    if (!value || loading) return;
    onSend(value);
    ref.current.value = '';
    ref.current.style.height = 'auto';
  };

  const autoResize = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-3">
      <div className="flex items-end gap-2">
        <textarea
          ref={ref}
          rows={1}
          onInput={autoResize}
          onKeyDown={handleKeyDown}
          disabled={loading}
          placeholder={t('chat.input_placeholder')}
          className={clsx(
            'flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800',
            'placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
            'disabled:bg-slate-50 disabled:text-slate-400 transition-colors',
          )}
        />
        <button
          onClick={submit}
          disabled={loading}
          className={clsx(
            'flex-shrink-0 h-9 w-9 rounded-xl flex items-center justify-center transition-colors',
            'bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed',
          )}
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
      <p className="text-xs text-slate-400 mt-1.5 px-1">{t('chat.shift_enter_hint')}</p>
    </div>
  );
}
