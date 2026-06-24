import { useState, useEffect } from 'react';
import {
  AlertTriangle, Hash, PiggyBank, CalendarClock,
  ArrowDownLeft, ArrowUpRight, FileClock, ChevronLeft, ChevronRight, X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { keepPreviousData } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { useFilters } from '../context/FilterContext';
import { useBankMovements, useBankGapDetail } from '../hooks/useReports';
import { useLanguage } from '../context/LanguageContext';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import DataTable from '../components/DataTable';
import ErrorBanner from '../components/ErrorBanner';
import {
  formatCurrency, formatCompact, formatDate, formatAxisCurrency,
} from '../utils/formatters';
import clsx from 'clsx';

const MOVEMENTS_PAGE_SIZE = 50;
const GAP_DETAIL_PAGE_SIZE = 50;

// Real-bank journal kind → small grey tag (clearing bank vs FX treasury vs notes).
function KindTag({ kind }) {
  const { t } = useTranslation();
  if (!kind || kind === 'clearing_bank') return null;
  return (
    <span className="ms-1 inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-500 align-middle">
      {t(`bank.kind_${kind}`)}
    </span>
  );
}

// "clean" (no gaps) = green, "has_gaps" = amber/rose.
function BankStatusPill({ status }) {
  const { t } = useTranslation();
  const cls = status === 'has_gaps' ? 'bg-rose-50 text-rose-700' : 'bg-emerald-50 text-emerald-700';
  return (
    <span className={clsx('inline-block px-2 py-0.5 rounded-full text-xs font-medium', cls)}>
      {t(`bank.${status === 'has_gaps' ? 'has_gaps' : 'clean'}`)}
    </span>
  );
}

// inbound (receipt → money in) green; outbound (payment → money out) amber.
function DirectionPill({ type }) {
  const { t } = useTranslation();
  const inbound = type === 'inbound';
  return (
    <span className={clsx(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
      inbound ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
    )}>
      {inbound ? <ArrowDownLeft className="h-3 w-3" /> : <ArrowUpRight className="h-3 w-3" />}
      {t(inbound ? 'bank.inbound' : 'bank.outbound')}
    </span>
  );
}

// Server-paginated movements table (the list is fetched page-by-page from the
// endpoint, NOT client-side like DataTable). Gap rows (unreconciled) are tinted;
// a prominent toggle flips gaps-only ↔ all movements and refetches.
function MovementsTable({ data, isFetching, gapsOnly, onToggle, offset, onPage }) {
  const { t } = useTranslation();
  const { isRTL } = useLanguage();
  const rows = data?.movements ?? [];
  const total = data?.movements_total_count ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = offset + rows.length;
  const PrevIcon = isRTL ? ChevronRight : ChevronLeft;
  const NextIcon = isRTL ? ChevronLeft : ChevronRight;

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      {/* Toolbar: gaps-only toggle + showing N of M */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 gap-3 flex-wrap">
        <div className="inline-flex rounded-lg border border-slate-200 overflow-hidden">
          <button
            onClick={() => onToggle(true)}
            className={clsx('px-3 py-1.5 text-xs font-medium transition-colors',
              gapsOnly ? 'bg-rose-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50')}
          >
            {t('bank.gaps_only')}
          </button>
          <button
            onClick={() => onToggle(false)}
            className={clsx('px-3 py-1.5 text-xs font-medium transition-colors border-s border-slate-200',
              !gapsOnly ? 'bg-primary-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50')}
          >
            {t('bank.all_movements')}
          </button>
        </div>
        <span className="text-xs text-slate-400">
          {t('bank.showing_n_of_m', { n: `${from}–${to}`, m: total.toLocaleString() })}
          {isFetching ? ` · ${t('common.loading')}` : ''}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['date', 'bank', 'partner', 'direction', 'amount', 'reconciled', 'matched', 'ref', 'state'].map((k) => (
                <th key={k} className={clsx('px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap',
                  k === 'amount' ? 'text-end' : 'text-start')}>
                  {t(`bank.col_${k}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-10 text-center text-sm text-slate-400">
                {t(gapsOnly ? 'bank.empty_gaps' : 'bank.empty_movements')}
              </td></tr>
            ) : rows.map((m) => (
              <tr key={m.id} className={clsx('border-b border-slate-50 transition-colors',
                !m.is_reconciled ? 'bg-rose-50/40 hover:bg-rose-50/70' : 'hover:bg-slate-50/60')}>
                <td className="px-4 py-2.5 text-slate-600" style={{ direction: 'ltr' }}>
                  {m.date ? formatDate(m.date) : '—'}
                </td>
                <td className="px-4 py-2.5 text-slate-700" dir="auto">
                  <span>{m.bank}</span>
                  {!m.is_bank_journal && (
                    <span className="ms-1 inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-400 align-middle">
                      {t('bank.non_bank_journal')}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-slate-600" dir="auto">{m.partner}</td>
                <td className="px-4 py-2.5"><DirectionPill type={m.payment_type} /></td>
                <td className="px-4 py-2.5 text-end tabular-nums text-slate-800 font-medium">
                  {formatCurrency(m.amount)}
                </td>
                <td className="px-4 py-2.5">
                  {m.is_reconciled
                    ? <span className="text-emerald-600 font-semibold">✓</span>
                    : <span className="text-rose-600 font-semibold">✗</span>}
                </td>
                <td className="px-4 py-2.5 text-slate-400 text-xs">
                  {m.is_matched ? '✓' : '—'}
                </td>
                <td className="px-4 py-2.5 text-slate-500 text-xs max-w-[14rem] truncate" dir="auto" title={m.ref}>
                  {m.ref || '—'}
                </td>
                <td className="px-4 py-2.5 text-slate-400 text-xs">{m.state}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Server pagination */}
      {total > MOVEMENTS_PAGE_SIZE && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
          <p className="text-xs text-slate-500">
            {t('bank.showing_n_of_m', { n: `${from}–${to}`, m: total.toLocaleString() })}
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPage(Math.max(0, offset - MOVEMENTS_PAGE_SIZE))}
              disabled={offset === 0 || isFetching}
              className="p-1.5 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <PrevIcon className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => onPage(offset + MOVEMENTS_PAGE_SIZE)}
              disabled={to >= total || isFetching}
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

// Per-bank GAP drill-down. Mounted only while a bank row's gap is open, so the lazy
// gap-detail query fires when opened. Lightweight modal (mirrors the Visa branch-detail
// modal): backdrop click and the X both close it. The movements list is server-paginated
// (oldest backlog at the top), exactly like the main movements list.
function GapDetailModal({ journal, companyId, onClose }) {
  const { t } = useTranslation();
  const { isRTL } = useLanguage();
  const [offset, setOffset] = useState(0);
  const { data, isLoading, isFetching, error } = useBankGapDetail(
    { company_id: companyId, journal_id: journal.journal_id, offset, limit: GAP_DETAIL_PAGE_SIZE },
    { placeholderData: keepPreviousData },
  );

  const header = data?.header ?? {};
  const rows = data?.movements ?? [];
  const total = data?.total_count ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = offset + rows.length;
  const PrevIcon = isRTL ? ChevronRight : ChevronLeft;
  const NextIcon = isRTL ? ChevronLeft : ChevronRight;

  // Fall back to the by_bank row values so the chips show instantly while the detail loads.
  const gapCount = header.gap_count != null ? header.gap_count : journal.gap_count;
  const gapAmount = header.gap_amount != null ? header.gap_amount : journal.gap_amount;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 sm:p-8"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-4xl my-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 p-5 border-b border-slate-100">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-slate-800" dir="auto">{header.bank || journal.bank}</h2>
              <span className="font-mono text-xs text-slate-400">{header.journal_code || journal.journal_code}</span>
              <BankStatusPill status="has_gaps" />
            </div>
            <p className="text-xs text-slate-400 mt-1">
              {t('bank.gap_detail_title')} · {t('bank.gap_detail_note')}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors flex-shrink-0"
            aria-label={t('common.close')}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-5">
          <ErrorBanner error={error} />

          {/* Mini KPIs — gap count / amount / inbound÷outbound split / oldest gap */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-slate-400">{t('bank.gap_count')}</p>
              <p className="text-lg font-bold text-rose-600 tabular-nums">{(gapCount ?? 0).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('bank.gap_amount')}</p>
              <p className="text-lg font-bold text-slate-800 tabular-nums">{formatCurrency(gapAmount ?? 0)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('bank.gap_inbound')} / {t('bank.gap_outbound')}</p>
              <p className="text-sm font-semibold tabular-nums mt-1.5">
                <span className="text-emerald-700">{formatCompact(header.gap_inbound_amount ?? 0)}</span>
                <span className="text-slate-300"> / </span>
                <span className="text-amber-700">{formatCompact(header.gap_outbound_amount ?? 0)}</span>
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('bank.oldest_gap')}</p>
              <p className="text-lg font-bold text-slate-800 tabular-nums" style={{ direction: 'ltr' }}>
                {header.oldest_gap_date ? formatDate(header.oldest_gap_date) : '—'}
              </p>
            </div>
          </div>

          {/* The unreconciled (gap) movements making up this bank's gap — oldest first */}
          <div className="border border-slate-200 rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 gap-3 flex-wrap">
              <span className="text-xs font-medium text-slate-500">{t('bank.gap_detail_subtitle')}</span>
              <span className="text-xs text-slate-400">
                {t('bank.showing_n_of_m', { n: `${from}–${to}`, m: total.toLocaleString() })}
                {isFetching ? ` · ${t('common.loading')}` : ''}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    {['date', 'partner', 'direction', 'amount', 'reconciled', 'matched', 'ref', 'state'].map((k) => (
                      <th key={k} className={clsx('px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap',
                        k === 'amount' ? 'text-end' : 'text-start')}>
                        {t(`bank.col_${k}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-slate-400">{t('common.loading')}</td></tr>
                  ) : rows.length === 0 ? (
                    <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-slate-400">{t('bank.gap_empty')}</td></tr>
                  ) : rows.map((m) => (
                    <tr key={m.id} className="border-b border-slate-50 bg-rose-50/40 hover:bg-rose-50/70 transition-colors">
                      <td className="px-4 py-2.5 text-slate-600" style={{ direction: 'ltr' }}>
                        {m.date ? formatDate(m.date) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-slate-600" dir="auto">{m.partner}</td>
                      <td className="px-4 py-2.5"><DirectionPill type={m.payment_type} /></td>
                      <td className="px-4 py-2.5 text-end tabular-nums text-slate-800 font-medium">{formatCurrency(m.amount)}</td>
                      <td className="px-4 py-2.5">
                        {m.is_reconciled
                          ? <span className="text-emerald-600 font-semibold">✓</span>
                          : <span className="text-rose-600 font-semibold">✗</span>}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 text-xs">{m.is_matched ? '✓' : '—'}</td>
                      <td className="px-4 py-2.5 text-slate-500 text-xs max-w-[14rem] truncate" dir="auto" title={m.ref}>
                        {m.ref || '—'}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 text-xs">{m.state}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Server pagination — mirrors the main movements list */}
            {total > GAP_DETAIL_PAGE_SIZE && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
                <p className="text-xs text-slate-500">
                  {t('bank.showing_n_of_m', { n: `${from}–${to}`, m: total.toLocaleString() })}
                </p>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setOffset(Math.max(0, offset - GAP_DETAIL_PAGE_SIZE))}
                    disabled={offset === 0 || isFetching}
                    className="p-1.5 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <PrevIcon className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => setOffset(offset + GAP_DETAIL_PAGE_SIZE)}
                    disabled={to >= total || isFetching}
                    className="p-1.5 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <NextIcon className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function BankMovements() {
  const { filters } = useFilters();
  const [applied, setApplied] = useState(filters);
  const [gapsOnly, setGapsOnly] = useState(true);
  const [offset, setOffset] = useState(0);
  const [openGapJournal, setOpenGapJournal] = useState(null);
  const { t } = useTranslation();

  // One endpoint returns summary + by_bank + suspense (gaps_only/offset-independent)
  // AND the paginated movements list. keepPreviousData stops the KPIs/tables from
  // flashing a skeleton on every toggle/page change.
  const query = { ...applied, gaps_only: gapsOnly, offset, limit: MOVEMENTS_PAGE_SIZE };
  const { data, isLoading, isFetching, error } = useBankMovements(query, {
    placeholderData: keepPreviousData,
  });

  // Reset movements pagination whenever the filter or the toggle changes.
  const onApply = (f) => { setApplied(f); setOffset(0); };
  const onToggle = (val) => { setGapsOnly(val); setOffset(0); };

  const summary = data?.summary ?? {};
  const byBank = data?.by_bank ?? [];
  const suspense = data?.suspense ?? [];
  const drafts = data?.draft_bank_moves ?? [];

  // gap_amount per bank (only banks carrying a gap). Horizontal bars fit Arabic names.
  const chartData = byBank
    .filter((b) => b.gap_amount > 0.005)
    .map((b) => ({ name: b.bank, gap: b.gap_amount }));

  const BANK_COLS = [
    { key: 'bank', header: t('bank.bank'), sortable: true, arabic: true,
      render: (r) => (
        <span dir="auto">
          <span className="font-mono text-xs text-slate-400 me-1">{r.journal_code}</span>
          {r.bank}<KindTag kind={r.kind} />
        </span>
      ), exportValue: (r) => `${r.journal_code} ${r.bank}` },
    { key: 'company', header: t('bank.company'), sortable: true, arabic: true, exportValue: (r) => r.company },
    { key: 'inbound_count', header: t('bank.inbound'), sortable: true, align: 'right',
      render: (r) => <span className="tabular-nums">{r.inbound_count.toLocaleString()}</span>, exportValue: (r) => r.inbound_count },
    { key: 'outbound_count', header: t('bank.outbound'), sortable: true, align: 'right',
      render: (r) => <span className="tabular-nums">{r.outbound_count.toLocaleString()}</span>, exportValue: (r) => r.outbound_count },
    { key: 'movements_amount', header: t('bank.movements_amount'), sortable: true, align: 'right',
      render: (r) => formatCurrency(r.movements_amount), exportValue: (r) => r.movements_amount },
    { key: 'gap_count', header: t('bank.gap_count'), sortable: true, align: 'right',
      render: (r) => (
        r.gap_count > 0 ? (
          <button
            onClick={() => setOpenGapJournal(r)}
            title={t('bank.gap_details')}
            className="underline decoration-dotted underline-offset-2 hover:decoration-solid focus:outline-none focus:ring-2 focus:ring-primary-300 rounded font-semibold text-rose-600 tabular-nums"
          >
            {r.gap_count.toLocaleString()}
          </button>
        ) : (
          <span className="text-slate-400 tabular-nums">{r.gap_count.toLocaleString()}</span>
        )
      ), exportValue: (r) => r.gap_count },
    { key: 'gap_amount', header: t('bank.gap_amount'), sortable: true, align: 'right',
      render: (r) => (
        r.gap_count > 0 ? (
          <button
            onClick={() => setOpenGapJournal(r)}
            title={t('bank.gap_details')}
            className="underline decoration-dotted underline-offset-2 hover:decoration-solid focus:outline-none focus:ring-2 focus:ring-primary-300 rounded font-semibold text-slate-800"
          >
            {formatCurrency(r.gap_amount)}
          </button>
        ) : (
          <span className="text-slate-400">{formatCurrency(r.gap_amount)}</span>
        )
      ), exportValue: (r) => r.gap_amount },
    { key: 'last_movement_date', header: t('bank.last_movement'), sortable: true,
      render: (r) => <span style={{ direction: 'ltr' }}>{r.last_movement_date ? formatDate(r.last_movement_date) : '—'}</span>,
      exportValue: (r) => r.last_movement_date || '' },
    { key: 'oldest_gap_date', header: t('bank.oldest_gap'), sortable: true,
      render: (r) => <span style={{ direction: 'ltr' }}>{r.oldest_gap_date ? formatDate(r.oldest_gap_date) : '—'}</span>,
      exportValue: (r) => r.oldest_gap_date || '' },
    { key: 'status', header: t('bank.status'), sortable: true,
      render: (r) => <BankStatusPill status={r.status} />, exportValue: (r) => r.status },
  ];

  return (
    <div className="space-y-6">
      <FilterPanel onApply={onApply} />

      {/* What this screen is — gaps = recorded-but-unreconciled bank movements; suspense
          = money parked in a clearing account. Excludes cash drawers (Area 1) & cards (Area 2). */}
      <p className="text-xs text-slate-500 leading-relaxed -mt-2">{t('bank.intro')}</p>

      {/* KPI cards — lead with the gap (the screen's purpose). All-time "as of today". */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title={t('bank.kpi_gap_amount')}
          value={summary.gap_amount != null ? formatCompact(summary.gap_amount) : '—'}
          icon={AlertTriangle}
          color="rose"
          loading={isLoading}
          subtitle={`${t('bank.on_bank_journals')}: ${summary.gap_amount_on_bank_journals != null ? formatCompact(summary.gap_amount_on_bank_journals) : '—'}${data?.cached ? ' · ' + t('common.cached') : ''}`}
        />
        <KPICard
          title={t('bank.kpi_gap_count')}
          value={summary.gap_count != null ? summary.gap_count.toLocaleString() : '—'}
          icon={Hash}
          color="amber"
          loading={isLoading}
          subtitle={`${t('bank.on_bank_journals')}: ${(summary.gap_count_on_bank_journals ?? 0).toLocaleString()}`}
        />
        <KPICard
          title={t('bank.kpi_suspense_net')}
          value={summary.suspense_net_balance != null ? formatCompact(summary.suspense_net_balance) : '—'}
          icon={PiggyBank}
          color="indigo"
          loading={isLoading}
          subtitle={`${summary.suspense_nonzero_lines ?? 0} ${t('bank.suspense_lines')}`}
        />
        <KPICard
          title={t('bank.kpi_oldest_gap')}
          value={summary.oldest_gap_date ? formatDate(summary.oldest_gap_date) : '—'}
          icon={CalendarClock}
          color="sky"
          loading={isLoading}
        />
      </div>

      <ErrorBanner error={error} />

      {/* Movement-volume context (date-windowed) — distinct from the all-time gap KPIs. */}
      {!isLoading && (
        <div className="bg-white border border-slate-200 rounded-xl px-5 py-4 grid grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <p className="text-xs text-slate-400">{t('bank.movements_in_window')}</p>
            <p className="text-lg font-bold text-slate-800 tabular-nums">{(summary.total_movements_count ?? 0).toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">{t('bank.inbound_amount')}</p>
            <p className="text-lg font-bold text-emerald-700 tabular-nums">{formatCompact(summary.total_inbound_amount ?? 0)}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">{t('bank.outbound_amount')}</p>
            <p className="text-lg font-bold text-amber-700 tabular-nums">{formatCompact(summary.total_outbound_amount ?? 0)}</p>
          </div>
        </div>
      )}

      {/* Gap amount per bank */}
      {!isLoading && chartData.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('bank.chart_title')}</h2>
          <ResponsiveContainer width="100%" height={Math.max(220, chartData.length * 34)}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 24, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={formatAxisCurrency} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={150} />
              <Tooltip formatter={(v) => formatCompact(v)} />
              <Bar dataKey="gap" name={t('bank.gap_amount')} fill="#e11d48" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Per-bank movements & gaps (27 real bank journals — Visa excluded) */}
      <div>
        <div className="flex items-center gap-2 flex-wrap mb-3">
          <h2 className="text-sm font-semibold text-slate-700">{t('bank.by_bank_title')}</h2>
          <span className="text-xs text-slate-400">· {t('bank.by_bank_note')}</span>
        </div>
        <DataTable
          columns={BANK_COLS}
          data={byBank}
          loading={isLoading}
          emptyMessage={t('bank.empty_bank')}
          filename="bank-movements-by-bank.csv"
        />
      </div>

      {/* Movements list (defaults to gaps-only; toggle flips to all movements) */}
      <div>
        <div className="flex items-center gap-2 flex-wrap mb-3">
          <h2 className="text-sm font-semibold text-slate-700">{t('bank.movements')}</h2>
          <span className="text-xs text-slate-400">· {gapsOnly ? t('bank.movements_gaps_note') : t('bank.movements_all_note')}</span>
        </div>
        <MovementsTable
          data={data}
          isFetching={isFetching}
          gapsOnly={gapsOnly}
          onToggle={onToggle}
          offset={offset}
          onPage={setOffset}
        />
      </div>

      {/* Suspense panel — a DIFFERENT gap type: money parked in a clearing account. */}
      <div>
        <div className="flex items-center gap-2 flex-wrap mb-3">
          <PiggyBank className="h-4 w-4 text-indigo-400" />
          <h2 className="text-sm font-semibold text-slate-700">{t('bank.suspense_title')}</h2>
          <span className="text-xs text-slate-400">· {t('bank.suspense_note')}</span>
        </div>
        {!isLoading && suspense.length > 0 ? (
          <div className="overflow-x-auto border border-slate-200 rounded-xl bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="px-4 py-2.5 text-start text-xs font-semibold text-slate-500 uppercase tracking-wide">{t('bank.account')}</th>
                  <th className="px-4 py-2.5 text-start text-xs font-semibold text-slate-500 uppercase tracking-wide">{t('bank.company')}</th>
                  <th className="px-4 py-2.5 text-end text-xs font-semibold text-slate-500 uppercase tracking-wide">{t('bank.suspense_net')}</th>
                  <th className="px-4 py-2.5 text-end text-xs font-semibold text-slate-500 uppercase tracking-wide">{t('bank.suspense_lines')}</th>
                  <th className="px-4 py-2.5 text-start text-xs font-semibold text-slate-500 uppercase tracking-wide">{t('bank.oldest_nonzero')}</th>
                </tr>
              </thead>
              <tbody>
                {suspense.map((s) => (
                  <tr key={s.account_id} className="border-b border-slate-50">
                    <td className="px-4 py-2.5 text-slate-700" dir="auto">
                      <span className="font-mono text-xs text-slate-400 me-1">{s.account_code}</span>{s.account_name}
                    </td>
                    <td className="px-4 py-2.5 text-slate-600" dir="auto">{s.company}</td>
                    <td className={clsx('px-4 py-2.5 text-end tabular-nums font-medium',
                      Math.abs(s.net_balance) > 0.005 ? 'text-slate-800' : 'text-slate-400')}>
                      {formatCurrency(s.net_balance)}
                    </td>
                    <td className="px-4 py-2.5 text-end tabular-nums text-slate-600">{s.nonzero_line_count.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-slate-500" style={{ direction: 'ltr' }}>
                      {s.oldest_nonzero_date ? formatDate(s.oldest_nonzero_date) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !isLoading && <p className="text-sm text-slate-400">{t('bank.empty_suspense')}</p>
        )}
      </div>

      {/* Draft bank entries — small awareness note (unposted bank journal entries). */}
      {!isLoading && (summary.draft_bank_moves_count ?? 0) > 0 && (
        <div className="bg-slate-50 border border-dashed border-slate-300 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1.5">
            <FileClock className="h-4 w-4 text-slate-400" />
            <h3 className="font-semibold text-slate-500 text-sm">{t('bank.draft_title')}</h3>
            <span className="text-xs text-slate-400">· {t('bank.draft_note')}</span>
          </div>
          <p className="text-xs text-slate-500">
            {drafts.map((d, i) => (
              <span key={d.company_id ?? i}>
                {i > 0 ? ' · ' : ''}
                <span dir="auto">{d.company}</span>: {d.count} ({formatCurrency(d.amount)})
              </span>
            ))}
          </p>
        </div>
      )}

      {/* Per-bank GAP drill-down (lazy — only fetched when a bank's gap is opened) */}
      {openGapJournal && (
        <GapDetailModal
          journal={openGapJournal}
          companyId={applied.company_id}
          onClose={() => setOpenGapJournal(null)}
        />
      )}
    </div>
  );
}
