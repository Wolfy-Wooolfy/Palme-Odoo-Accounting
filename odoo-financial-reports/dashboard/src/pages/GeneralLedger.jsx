import { useState, useCallback, useRef } from 'react';
import { BookMarked, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useGeneralLedger } from '../hooks/useReports';
import { searchAccounts } from '../api/reports';
import { useFilters } from '../context/FilterContext';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import EmptyState from '../components/EmptyState';
import { formatCurrency, formatCompact } from '../utils/formatters';
import { useLanguage } from '../context/LanguageContext';
import clsx from 'clsx';

const GL_COLS = [
  { key: 'date', header: 'Date', sortable: false },
  { key: 'move_name', header: 'Entry', sortable: false },
  { key: 'label', header: 'Label', sortable: false, arabic: true },
  { key: 'partner', header: 'Partner', sortable: false },
  { key: 'debit', header: 'Debit', sortable: false, align: 'right', type: 'currency' },
  { key: 'credit', header: 'Credit', sortable: false, align: 'right', type: 'currency' },
  { key: 'running_balance', header: 'Balance', sortable: false, align: 'right', type: 'currency', colored: true },
];

function AccountSearch({ onSelect, t }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const timerRef = useRef(null);

  const search = useCallback((q) => {
    clearTimeout(timerRef.current);
    if (q.length < 1) { setResults([]); return; }
    setLoading(true);
    timerRef.current = setTimeout(async () => {
      try {
        const res = await searchAccounts(q, 30);
        setResults(res);
      } finally {
        setLoading(false);
      }
    }, 300);
  }, []);

  const select = (acc) => {
    setSelected(acc);
    setQuery(`${acc.code} — ${acc.name}`);
    setResults([]);
    onSelect(acc);
  };

  return (
    <div className="relative">
      <label className="text-xs font-medium text-slate-500 block mb-1">{t('general_ledger.select_account')}</label>
      <div className="relative">
        <Search className="absolute start-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); search(e.target.value); }}
          placeholder={t('general_ledger.search_account')}
          className="w-full ps-9 pe-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-300"
        />
      </div>
      {results.length > 0 && (
        <div className="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
          {results.map((acc) => (
            <button
              key={acc.id}
              onClick={() => select(acc)}
              className="w-full text-start px-4 py-2.5 text-sm hover:bg-slate-50 border-b border-slate-50 last:border-0"
            >
              <span className="font-mono text-xs text-slate-500 me-2">{acc.code}</span>
              <span className="text-slate-700">{acc.name}</span>
              <span className="text-xs text-slate-400 ms-2">({acc.account_type})</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function GeneralLedger() {
  const { filters } = useFilters();
  const { t } = useTranslation();
  const { isRTL } = useLanguage();
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [applied, setApplied] = useState(filters);
  const [offset, setOffset] = useState(0);
  const LIMIT = 200;

  const glFilter = selectedAccount
    ? {
        account_id: selectedAccount.id,
        date_from: applied.date_from,
        date_to: applied.date_to,
        company_id: applied.company_id,
        posted_only: applied.posted_only,
        offset,
        limit: LIMIT,
      }
    : null;

  const { data, isLoading, error } = useGeneralLedger(glFilter);

  const handleApply = (f) => {
    setApplied(f);
    setOffset(0);
  };

  const PrevIcon = isRTL ? ChevronRight : ChevronLeft;
  const NextIcon = isRTL ? ChevronLeft : ChevronRight;

  const lines = data?.lines ?? [];
  const pagination = data?.pagination;

  return (
    <div className="space-y-6">
      <FilterPanel onApply={handleApply} />

      {/* Account selector + info */}
      <div className="bg-white border border-slate-200 rounded-xl px-5 py-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-end">
          <AccountSearch onSelect={(acc) => { setSelectedAccount(acc); setOffset(0); }} t={t} />
          {selectedAccount && (
            <div className="flex items-center gap-3 text-sm text-slate-600">
              <BookMarked className="h-4 w-4 text-primary-500 flex-shrink-0" />
              <div>
                <span className="font-mono text-xs text-slate-500 me-1">{selectedAccount.code}</span>
                <span className="font-medium">{selectedAccount.name}</span>
                <span className="text-xs text-slate-400 ms-1">({selectedAccount.account_type})</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {!selectedAccount && <EmptyState message={t('general_ledger.no_account')} icon={BookMarked} />}

      {/* KPIs */}
      {selectedAccount && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            title={t('general_ledger.opening_balance')}
            value={formatCompact(data?.opening_balance)}
            color={(data?.opening_balance ?? 0) >= 0 ? 'indigo' : 'rose'}
            loading={isLoading}
          />
          <KPICard
            title={t('general_ledger.closing_balance')}
            value={formatCompact(data?.closing_balance)}
            color={(data?.closing_balance ?? 0) >= 0 ? 'emerald' : 'rose'}
            loading={isLoading}
          />
          <KPICard
            title={t('general_ledger.total_lines')}
            value={data?.total_lines?.toLocaleString()}
            color="sky"
            loading={isLoading}
          />
          <KPICard
            title={t('kpi.as_of', { date: '' }).trim()}
            value={`${applied.date_from} → ${applied.date_to}`}
            color="indigo"
            loading={false}
          />
        </div>
      )}

      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">
          {error.response?.data?.detail || error.message}
        </div>
      )}

      {/* Table */}
      {selectedAccount && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  {GL_COLS.map((col) => (
                    <th key={col.key} className={clsx(
                      'px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap',
                      col.align === 'right' ? 'text-end' : 'text-start'
                    )}>
                      {t(`general_ledger.${col.key === 'move_name' ? 'entry' : col.key === 'running_balance' ? 'running_balance' : col.key}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {isLoading
                  ? Array.from({ length: 8 }).map((_, i) => (
                      <tr key={i} className="animate-pulse border-b border-slate-50">
                        {GL_COLS.map((c) => (
                          <td key={c.key} className="px-4 py-3">
                            <div className="h-4 bg-slate-200 rounded" />
                          </td>
                        ))}
                      </tr>
                    ))
                  : lines.length === 0
                  ? (
                    <tr><td colSpan={GL_COLS.length}>
                      <EmptyState message={t('general_ledger.empty')} />
                    </td></tr>
                  )
                  : lines.map((line) => (
                    <tr key={line.id} className="border-b border-slate-50 hover:bg-slate-50/60">
                      <td className="px-4 py-2.5 text-slate-600 whitespace-nowrap">{line.date}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-primary-600">{line.move_name}</td>
                      <td className="px-4 py-2.5 text-slate-700 max-w-xs truncate" dir="auto">{line.label || '—'}</td>
                      <td className="px-4 py-2.5 text-slate-500 max-w-xs truncate">{line.partner || '—'}</td>
                      <td className="px-4 py-2.5 text-end tabular-nums text-slate-700">
                        {line.debit ? formatCurrency(line.debit) : ''}
                      </td>
                      <td className="px-4 py-2.5 text-end tabular-nums text-slate-700">
                        {line.credit ? formatCurrency(line.credit) : ''}
                      </td>
                      <td className={clsx(
                        'px-4 py-2.5 text-end tabular-nums font-medium',
                        line.running_balance >= 0 ? 'text-emerald-700' : 'text-rose-600'
                      )}>
                        {formatCurrency(line.running_balance)}
                      </td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {!isLoading && data?.total_lines > LIMIT && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
              <p className="text-xs text-slate-500">
                {offset + 1}–{Math.min(offset + LIMIT, data.total_lines)} / {data.total_lines.toLocaleString()}
              </p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
                  disabled={offset === 0}
                  className="p-1.5 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40"
                >
                  <PrevIcon className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setOffset((o) => o + LIMIT)}
                  disabled={!pagination?.has_more}
                  className="p-1.5 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40"
                >
                  <NextIcon className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
