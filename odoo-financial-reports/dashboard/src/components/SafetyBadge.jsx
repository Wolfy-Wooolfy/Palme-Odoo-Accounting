import { useState } from 'react';
import { Shield, X, CheckCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSafetyStatus } from '../hooks/useMeta';

const LAYER_KEYS = ['layer_1','layer_2','layer_3','layer_4','layer_5','layer_6','layer_7'];

export default function SafetyBadge() {
  const [open, setOpen] = useState(false);
  const { data } = useSafetyStatus();
  const { t } = useTranslation();

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-100 transition-colors"
      >
        <Shield className="h-3.5 w-3.5" />
        {t('safety.badge')}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="bg-emerald-100 rounded-xl p-2.5">
                  <Shield className="h-5 w-5 text-emerald-600" />
                </div>
                <div>
                  <h2 className="font-semibold text-slate-900">{t('safety.modal_title')}</h2>
                  <p className="text-xs text-slate-500">{t('safety.subtitle')}</p>
                </div>
              </div>
              <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 space-y-2">
              {LAYER_KEYS.map((key, i) => (
                <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-slate-50">
                  <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                  <span className="text-sm text-slate-700">
                    <span className="font-medium text-slate-500 me-2">
                      {t('settings.layer', { n: i + 1 })}
                    </span>
                    {t(`safety.${key}`)}
                  </span>
                </div>
              ))}
            </div>

            {data && (
              <div className="px-6 pb-6">
                <p className="text-xs text-slate-500 mb-2 font-medium">{t('safety.allowed_methods')}</p>
                <div className="flex flex-wrap gap-1.5">
                  {data.allowed_methods?.map((m) => (
                    <span key={m} className="text-xs bg-primary-50 text-primary-700 rounded px-2 py-0.5 font-mono">{m}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
