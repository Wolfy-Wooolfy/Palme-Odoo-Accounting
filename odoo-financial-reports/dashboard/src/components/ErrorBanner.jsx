import { AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

function extractMessage(error) {
  if (typeof error === 'string') return error;

  const detail = error?.response?.data?.detail;
  if (detail) {
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e) => {
          const loc = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : '';
          return loc ? `${loc}: ${e.msg || 'invalid'}` : (e.msg || 'invalid');
        })
        .join(' • ');
    }
    return JSON.stringify(detail);
  }

  if (error?.message) return error.message;
  return String(error);
}

export default function ErrorBanner({ error, onRetry }) {
  const { t } = useTranslation();
  if (!error) return null;

  return (
    <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-start gap-3">
      <AlertCircle className="h-5 w-5 text-rose-500 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-rose-900">{t('common.error')}</p>
        <p className="text-sm text-rose-700 mt-1 break-words">{extractMessage(error)}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-2 text-xs font-medium text-rose-700 hover:text-rose-900 underline"
          >
            {t('common.retry', 'Retry')}
          </button>
        )}
      </div>
    </div>
  );
}
