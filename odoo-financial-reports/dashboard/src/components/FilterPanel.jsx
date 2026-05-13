import { useState } from 'react';
import { SlidersHorizontal, ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';
import { DATE_PRESETS, matchesPreset } from '../utils/dateHelpers';
import { useCompanies } from '../hooks/useMeta';
import { useFilters } from '../context/FilterContext';

// Map preset labels to i18n keys
const PRESET_KEYS = {
  'This Month': 'filters.this_month',
  'Last Month': 'filters.last_month',
  'This Quarter': 'filters.this_quarter',
  'YTD': 'filters.ytd',
  'This Year': 'filters.this_year',
  'Last Year': 'filters.last_year',
};

export default function FilterPanel({ onApply, hideDate = false }) {
  const { filters, setFilters } = useFilters();
  const { data: companies = [] } = useCompanies();
  const [local, setLocal] = useState({ ...filters });
  const [open, setOpen] = useState(true);
  const { t } = useTranslation();

  const activePreset = matchesPreset(local.date_from, local.date_to);

  const apply = () => {
    setFilters(local);
    onApply?.(local);
  };

  const setPreset = (preset) => {
    const vals = preset.getValue();
    setLocal((prev) => ({ ...prev, ...vals }));
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl mb-5">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 text-sm font-medium text-slate-700 hover:bg-slate-50 rounded-xl transition-colors"
      >
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-slate-400" />
          {t('filters.title')}
          <span className="text-xs text-slate-400 font-normal">
            {local.date_from} → {local.date_to}
            {local.company_id ? ` · #${local.company_id}` : ` · ${t('filters.all_companies')}`}
          </span>
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
      </button>

      {open && (
        <div className="border-t border-slate-100 px-5 py-4 space-y-4">
          {!hideDate && (
            <>
              <div>
                <p className="text-xs font-medium text-slate-500 mb-2">{t('filters.quick_select')}</p>
                <div className="flex flex-wrap gap-2">
                  {DATE_PRESETS.map((p) => (
                    <button
                      key={p.label}
                      onClick={() => setPreset(p)}
                      className={clsx(
                        'text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors',
                        activePreset === p.label
                          ? 'bg-primary-600 text-white border-primary-600'
                          : 'border-slate-200 text-slate-600 hover:border-primary-300 hover:text-primary-600'
                      )}
                    >
                      {t(PRESET_KEYS[p.label] || p.label)}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-slate-500 block mb-1">{t('filters.from')}</label>
                  <input
                    type="date"
                    value={local.date_from}
                    onChange={(e) => setLocal((p) => ({ ...p, date_from: e.target.value }))}
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-300"
                    style={{ direction: 'ltr' }}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-500 block mb-1">{t('filters.to')}</label>
                  <input
                    type="date"
                    value={local.date_to}
                    onChange={(e) => setLocal((p) => ({ ...p, date_to: e.target.value }))}
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-300"
                    style={{ direction: 'ltr' }}
                  />
                </div>
              </div>
            </>
          )}

          <div className="flex flex-wrap items-center gap-4">
            <div className="flex-1 min-w-48">
              <label className="text-xs font-medium text-slate-500 block mb-1">{t('filters.company')}</label>
              <select
                value={local.company_id ?? ''}
                onChange={(e) => setLocal((p) => ({ ...p, company_id: e.target.value ? +e.target.value : null }))}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-300 bg-white"
              >
                <option value="">{t('filters.all_companies')}</option>
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2 mt-4">
              <input
                id="posted-only"
                type="checkbox"
                checked={local.posted_only}
                onChange={(e) => setLocal((p) => ({ ...p, posted_only: e.target.checked }))}
                className="rounded border-slate-300 text-primary-600 focus:ring-primary-300"
              />
              <label htmlFor="posted-only" className="text-sm text-slate-700 select-none">
                {t('filters.posted_only')}
              </label>
            </div>

            <button
              onClick={apply}
              className="mt-4 px-6 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors"
            >
              {t('common.apply')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
