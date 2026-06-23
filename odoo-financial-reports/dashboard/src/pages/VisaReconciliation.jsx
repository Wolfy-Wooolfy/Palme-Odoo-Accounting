import { useState } from 'react';
import { Wallet, AlertTriangle, Clock, CheckCircle2, Archive } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { useFilters } from '../context/FilterContext';
import { useVisaReconciliation } from '../hooks/useReports';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import DataTable from '../components/DataTable';
import ErrorBanner from '../components/ErrorBanner';
import {
  formatCurrency, formatCompact, formatDate, formatAxisCurrency,
} from '../utils/formatters';
import clsx from 'clsx';

// Status → pill colour (ok=green, due_soon=amber, late=red, manual=neutral).
// Late rows also sort to the top (backend) and show a bold-red working-days cell.
const STATUS_STYLE = {
  ok: 'bg-emerald-50 text-emerald-700',
  due_soon: 'bg-amber-50 text-amber-700',
  late: 'bg-rose-50 text-rose-700',
  manual: 'bg-slate-100 text-slate-600',
};

function StatusPill({ status }) {
  const { t } = useTranslation();
  return (
    <span className={clsx(
      'inline-block px-2 py-0.5 rounded-full text-xs font-medium',
      STATUS_STYLE[status] || STATUS_STYLE.ok
    )}>
      {t(`visa.status_${status}`)}
    </span>
  );
}

export default function VisaReconciliation() {
  const { filters } = useFilters();
  const [applied, setApplied] = useState(filters);
  const { data, isLoading, error } = useVisaReconciliation(applied);
  const { t } = useTranslation();

  const summary = data?.summary ?? {};
  const byBranch = data?.by_branch ?? [];
  const dailyDetail = data?.daily_detail ?? [];
  const legacy = data?.legacy_awareness ?? {};

  // Pending per branch (active only — the manual arabisck row carries a negative
  // over-credit that would distort the chart). Horizontal bars fit Arabic names.
  const chartData = byBranch
    .filter((b) => !b.manually_handled && Math.abs(b.pending) > 0.005)
    .map((b) => ({ name: b.branch, pending: b.pending }));

  const BRANCH_COLS = [
    { key: 'branch', header: t('visa.branch'), sortable: true, arabic: true, exportValue: (r) => r.branch },
    { key: 'journal_code', header: t('visa.journal_code'), sortable: true,
      render: (r) => <span className="font-mono text-xs text-slate-500">{r.journal_code}</span>,
      exportValue: (r) => r.journal_code },
    { key: 'collected', header: t('visa.collected'), sortable: true, align: 'right',
      render: (r) => formatCurrency(r.collected), exportValue: (r) => r.collected },
    { key: 'confirmed', header: t('visa.confirmed'), sortable: true, align: 'right',
      render: (r) => formatCurrency(r.confirmed), exportValue: (r) => r.confirmed },
    { key: 'pending', header: t('visa.pending'), sortable: true, align: 'right',
      render: (r) => (
        <span className={r.pending > 0.005 ? 'font-semibold text-slate-800' : 'text-slate-400'}>
          {formatCurrency(r.pending)}
        </span>
      ), exportValue: (r) => r.pending },
    { key: 'oldest_unconfirmed_stop_at', header: t('visa.oldest_unconfirmed'), sortable: true,
      render: (r) => <span style={{ direction: 'ltr' }}>{r.oldest_unconfirmed_stop_at ? formatDate(r.oldest_unconfirmed_stop_at) : '—'}</span>,
      exportValue: (r) => r.oldest_unconfirmed_stop_at || '' },
    { key: 'working_days_since_oldest_unconfirmed', header: t('visa.working_days_waiting'), sortable: true, align: 'right',
      render: (r) => (
        <span className={r.status === 'late' ? 'font-bold text-rose-600' : 'text-slate-600'}>
          {r.working_days_since_oldest_unconfirmed || 0} {t('visa.days_unit')}
        </span>
      ), exportValue: (r) => r.working_days_since_oldest_unconfirmed || 0 },
    { key: 'last_confirmation_date', header: t('visa.last_confirmation'), sortable: true,
      render: (r) => <span style={{ direction: 'ltr' }}>{r.last_confirmation_date ? formatDate(r.last_confirmation_date) : '—'}</span>,
      exportValue: (r) => r.last_confirmation_date || '' },
    { key: 'status', header: t('visa.status'), sortable: true,
      render: (r) => <StatusPill status={r.status} />, exportValue: (r) => r.status },
  ];

  const DAILY_COLS = [
    { key: 'date', header: t('visa.date'), sortable: true,
      render: (r) => <span style={{ direction: 'ltr' }}>{formatDate(r.date)}</span>, exportValue: (r) => r.date },
    { key: 'branch', header: t('visa.branch'), sortable: true, arabic: true, exportValue: (r) => r.branch },
    { key: 'collected', header: t('visa.collected'), sortable: true, align: 'right',
      render: (r) => formatCurrency(r.collected), exportValue: (r) => r.collected },
    { key: 'confirmed', header: t('visa.confirmed'), sortable: true, align: 'right',
      render: (r) => formatCurrency(r.confirmed), exportValue: (r) => r.confirmed },
    { key: 'net', header: t('visa.net'), sortable: true, align: 'right',
      render: (r) => formatCurrency(r.net), exportValue: (r) => r.net },
  ];

  const lateCount = summary.late_branches_count ?? 0;

  return (
    <div className="space-y-6">
      <FilterPanel onApply={setApplied} />

      {/* KPI cards (from summary — running balance "as of today", date-independent) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title={t('visa.total_pending')}
          value={summary.total_pending != null ? formatCompact(summary.total_pending) : '—'}
          icon={Wallet}
          color="indigo"
          loading={isLoading}
          subtitle={`${summary.active_branches_count ?? 0} ${t('visa.active_branches')}${data?.cached ? ' · ' + t('common.cached') : ''}`}
        />
        <KPICard
          title={t('visa.late_branches')}
          value={lateCount.toLocaleString()}
          icon={lateCount > 0 ? AlertTriangle : CheckCircle2}
          color={lateCount > 0 ? 'rose' : 'emerald'}
          loading={isLoading}
        />
        <KPICard
          title={t('visa.oldest_unconfirmed_wd')}
          value={summary.oldest_unconfirmed_working_days != null
            ? `${summary.oldest_unconfirmed_working_days} ${t('visa.days_unit')}`
            : '—'}
          icon={Clock}
          color="amber"
          loading={isLoading}
          subtitle={summary.oldest_unconfirmed_stop_at ? formatDate(summary.oldest_unconfirmed_stop_at) : undefined}
        />
        <KPICard
          title={t('visa.last_confirmation')}
          value={summary.last_confirmation_date ? formatDate(summary.last_confirmation_date) : '—'}
          icon={CheckCircle2}
          color="sky"
          loading={isLoading}
        />
      </div>

      <ErrorBanner error={error} />

      {/* Pending per branch */}
      {!isLoading && chartData.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('visa.chart_title')}</h2>
          <ResponsiveContainer width="100%" height={Math.max(220, chartData.length * 34)}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 24, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={formatAxisCurrency} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={150} />
              <Tooltip formatter={(v) => formatCompact(v)} />
              <Bar dataKey="pending" name={t('visa.pending')} fill="#4f46e5" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Per-branch reconciliation (running balance — date-independent). Rendered
          unconditionally — DataTable shows a skeleton while loading and its own
          empty state when there are no rows (e.g. a company with no Visa workflow). */}
      <div>
        <div className="flex items-center gap-2 flex-wrap mb-3">
          <h2 className="text-sm font-semibold text-slate-700">{t('visa.by_branch_title')}</h2>
          <span className="text-xs text-slate-400">· {t('visa.by_branch_note')}</span>
        </div>
        <DataTable
          columns={BRANCH_COLS}
          data={byBranch}
          loading={isLoading}
          emptyMessage={t('visa.empty_branch')}
          filename="visa-reconciliation-by-branch.csv"
        />
      </div>

      {/* Legacy (company 1) — awareness only, visually de-emphasised. Hidden when
          viewing company 1 itself (the table above already IS that pile). */}
      {!isLoading && data?.company_id !== 1 && (legacy.account_count ?? 0) > 0 && (
        <div className="bg-slate-50 border border-dashed border-slate-300 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Archive className="h-4 w-4 text-slate-400" />
            <h3 className="font-semibold text-slate-500 text-sm">{t('visa.legacy_title')}</h3>
            {legacy.stalled && (
              <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-slate-200 text-slate-600">
                {t('visa.legacy_stalled')}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-3">
            <div>
              <p className="text-xs text-slate-400">{t('visa.legacy_net_pending')}</p>
              <p className="text-lg font-bold text-slate-600 tabular-nums">{formatCompact(legacy.total_net_pending ?? 0)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('visa.legacy_last_confirmation')}</p>
              <p className="text-lg font-bold text-slate-600 tabular-nums" style={{ direction: 'ltr' }}>
                {legacy.last_confirmation_date ? formatDate(legacy.last_confirmation_date) : '—'}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('visa.legacy_accounts')}</p>
              <p className="text-lg font-bold text-slate-600 tabular-nums">{legacy.account_count ?? 0}</p>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-3 leading-relaxed">{t('visa.legacy_note')}</p>
        </div>
      )}

      {/* Daily detail (driven by the date filter) */}
      <div>
        <div className="flex items-center gap-2 flex-wrap mb-3">
          <h2 className="text-sm font-semibold text-slate-700">{t('visa.daily_detail')}</h2>
          <span className="text-xs text-slate-400">· {t('visa.daily_detail_note')}</span>
        </div>
        <DataTable
          columns={DAILY_COLS}
          data={dailyDetail}
          loading={isLoading}
          emptyMessage={t('visa.empty_daily')}
          filename={`visa-daily-${applied.date_from}-${applied.date_to}.csv`}
        />
      </div>
    </div>
  );
}
