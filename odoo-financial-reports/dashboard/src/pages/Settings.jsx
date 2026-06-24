import { ExternalLink, RefreshCw, Trash2, CheckCircle, Shield, Database, Wifi } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSafetyStatus, useCacheStats, useClearCache } from '../hooks/useMeta';
import LoadingSpinner from '../components/LoadingSpinner';

const LAYER_KEYS = ['layer_1','layer_2','layer_3','layer_4','layer_5','layer_6','layer_7'];

export default function Settings() {
  const { data: safety, isLoading: safetyLoading } = useSafetyStatus();
  const { data: cacheStats, isLoading: cacheLoading, refetch: refetchCache } = useCacheStats();
  const clearMutation = useClearCache();
  const { t } = useTranslation();

  return (
    <div className="max-w-3xl space-y-6">

      {/* Connection */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
          <Wifi className="h-4 w-4 text-primary-500" />
          <h2 className="font-semibold text-slate-700">{t('settings.connection')}</h2>
        </div>
        <div className="px-6 py-4 space-y-3">
          <Row label={t('settings.odoo_url')} value="https://kamahtech-palme.odoo.com" />
          <Row label={t('settings.database')} value="kamahtech-palme-prod-13407418" />
          <Row label={t('settings.version')} value="17.0+e Enterprise" />
          <Row label={t('settings.auth')} value="XML-RPC with API key" />
          <Row label={t('settings.mode')} value={<span className="bg-emerald-100 text-emerald-700 text-xs font-semibold px-2 py-0.5 rounded-full">{t('safety.badge')}</span>} />
          <div className="pt-2">
            <a
              href="http://127.0.0.1:8200/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-primary-600 hover:text-primary-700 font-medium"
            >
              {t('settings.api_docs')} <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </div>

      {/* Safety layers */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
          <Shield className="h-4 w-4 text-emerald-500" />
          <h2 className="font-semibold text-slate-700">{t('settings.safety')}</h2>
          <span className="ms-auto text-xs bg-emerald-100 text-emerald-700 font-semibold px-2 py-0.5 rounded-full">{t('settings.layers_active')}</span>
        </div>
        <div className="px-6 py-4 space-y-2">
          {LAYER_KEYS.map((key, i) => (
            <div key={i} className="flex items-center gap-3 py-2 border-b border-slate-50 last:border-0">
              <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0" />
              <span className="text-xs text-slate-500 font-medium w-14">{t('settings.layer', { n: i + 1 })}</span>
              <span className="text-sm text-slate-700">{t(`safety.${key}`)}</span>
            </div>
          ))}
        </div>
        {safety && (
          <div className="border-t border-slate-100 px-6 py-4">
            <p className="text-xs font-medium text-slate-500 mb-2">{t('settings.allowed_methods')} ({safety.allowed_methods?.length})</p>
            <div className="flex flex-wrap gap-1.5">
              {safety.allowed_methods?.map((m) => (
                <span key={m} className="font-mono text-xs bg-slate-100 text-slate-600 rounded px-2 py-0.5">{m}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Cache */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
          <Database className="h-4 w-4 text-sky-500" />
          <h2 className="font-semibold text-slate-700">{t('settings.cache')}</h2>
          <button
            onClick={() => refetchCache()}
            className="ms-auto text-slate-400 hover:text-slate-600"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        <div className="px-6 py-4 space-y-3">
          {cacheLoading ? (
            <LoadingSpinner size="sm" />
          ) : cacheStats ? (
            <>
              <Row label={t('settings.cache_total')} value={cacheStats.total} />
              <Row label={t('settings.cache_valid')} value={<span className="text-emerald-700 font-medium">{cacheStats.valid}</span>} />
              <Row label={t('settings.cache_expired')} value={cacheStats.expired} />
            </>
          ) : null}
          <div className="pt-2">
            <button
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-lg text-sm font-medium hover:bg-rose-100 transition-colors disabled:opacity-60"
            >
              <Trash2 className="h-4 w-4" />
              {clearMutation.isPending ? t('settings.clearing') : t('settings.clear_cache')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-50 last:border-0">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm text-slate-800 font-medium text-end">{value}</span>
    </div>
  );
}
