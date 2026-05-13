import { useState, useMemo } from 'react';
import { ChevronUp, ChevronDown, Search, Download, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLanguage } from '../context/LanguageContext';
import clsx from 'clsx';
import { SkeletonRow } from './LoadingSpinner';
import EmptyState from './EmptyState';
import { exportToCSV, formatCurrency } from '../utils/formatters';

const PAGE_SIZE = 50;

export default function DataTable({ columns, data = [], loading = false, filename = 'export.csv', emptyMessage }) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const { t } = useTranslation();
  const { isRTL } = useLanguage();

  const handleSort = (key) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('asc'); }
    setPage(1);
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return data;
    const q = search.toLowerCase();
    return data.filter((row) =>
      columns.some((col) => {
        const v = row[col.key];
        return v != null && String(v).toLowerCase().includes(q);
      })
    );
  }, [data, search, columns]);

  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    return [...filtered].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc'
        ? String(av ?? '').localeCompare(String(bv ?? ''))
        : String(bv ?? '').localeCompare(String(av ?? ''));
    });
  }, [filtered, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageData = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const SortIcon = ({ col }) => {
    if (!col.sortable) return null;
    if (sortKey !== col.key) return <ChevronUp className="h-3 w-3 text-slate-300 ms-1" />;
    return sortDir === 'asc'
      ? <ChevronUp className="h-3 w-3 text-primary-500 ms-1" />
      : <ChevronDown className="h-3 w-3 text-primary-500 ms-1" />;
  };

  // In RTL, prev/next arrows flip
  const PrevIcon = isRTL ? ChevronRight : ChevronLeft;
  const NextIcon = isRTL ? ChevronLeft : ChevronRight;

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute start-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder={t('common.search')}
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full ps-9 pe-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-300"
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">
            {filtered.length.toLocaleString()} {t('common.rows', { count: filtered.length })}
          </span>
          <button
            onClick={() => exportToCSV(sorted, columns, filename)}
            className="flex items-center gap-1.5 text-xs border border-slate-200 rounded-lg px-3 py-1.5 text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            {t('common.export_csv')}
          </button>
        </div>
      </div>

      {/* Table — charts stay LTR, but table follows document direction */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => col.sortable && handleSort(col.key)}
                  className={clsx(
                    'px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap',
                    col.align === 'right' ? 'text-end' : 'text-start',
                    col.sortable && 'cursor-pointer hover:text-slate-700 select-none'
                  )}
                  style={col.width ? { width: col.width } : undefined}
                >
                  <span className="inline-flex items-center">
                    {col.header}
                    <SortIcon col={col} />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} cols={columns.length} />)
              : pageData.length === 0
              ? (
                <tr>
                  <td colSpan={columns.length}>
                    <EmptyState message={emptyMessage} />
                  </td>
                </tr>
              )
              : pageData.map((row, i) => (
                <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                  {columns.map((col) => {
                    const val = row[col.key];
                    const isNum = col.type === 'currency';
                    const isColored = col.colored;
                    const colorClass = isColored
                      ? (val ?? 0) >= 0 ? 'text-emerald-700 font-medium' : 'text-rose-600 font-medium'
                      : '';
                    return (
                      <td
                        key={col.key}
                        dir={col.arabic ? 'auto' : undefined}
                        className={clsx(
                          'px-4 py-3 text-slate-700',
                          col.align === 'right' ? 'text-end tabular-nums' : '',
                          col.className,
                          colorClass
                        )}
                      >
                        {col.render
                          ? col.render(row)
                          : isNum
                          ? formatCurrency(val)
                          : (val ?? '—')}
                      </td>
                    );
                  })}
                </tr>
              ))
            }
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!loading && totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
          <p className="text-xs text-slate-500">
            {t('common.page_of', { page, total: totalPages })} · {sorted.length.toLocaleString()} {t('common.rows', { count: sorted.length })}
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-1.5 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <PrevIcon className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-1.5 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <NextIcon className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
