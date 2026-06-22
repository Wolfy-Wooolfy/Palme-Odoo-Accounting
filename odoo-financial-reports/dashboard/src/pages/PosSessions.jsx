import { useState } from 'react';
import { DoorOpen, AlertTriangle, Clock, LifeBuoy } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { useFilters } from '../context/FilterContext';
import { usePosSessions } from '../hooks/useReports';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import DataTable from '../components/DataTable';
import EmptyState from '../components/EmptyState';
import ErrorBanner from '../components/ErrorBanner';
import { formatDate } from '../utils/formatters';
import clsx from 'clsx';

// Severity tiers colour the "Open for" cell + row tint (ok=neutral, warning=amber, critical=red).
const SEV_TEXT = {
  ok: 'text-slate-600',
  warning: 'text-amber-600 font-semibold',
  critical: 'text-rose-600 font-bold',
};
const SEV_ROW = {
  ok: 'hover:bg-slate-50/60',
  warning: 'bg-amber-50/40 hover:bg-amber-50/70',
  critical: 'bg-rose-50/50 hover:bg-rose-50/80',
};

// age_hours -> "Xd Yh"
function fmtAge(ageHours) {
  const total = Math.max(0, Math.round(Number(ageHours) || 0));
  const d = Math.floor(total / 24);
  const h = total % 24;
  return d > 0 ? `${d}d ${h}h` : `${h}h`;
}

function DisciplinePill({ flag }) {
  const { t } = useTranslation();
  const good = flag === 'good';
  return (
    <span className={clsx(
      'inline-block px-2 py-0.5 rounded-full text-xs font-medium',
      good ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
    )}>
      {good ? t('pos.discipline_good') : t('pos.discipline_attention')}
    </span>
  );
}

function StatusPill({ state }) {
  const { t } = useTranslation();
  const label = state === 'closing_control' ? t('pos.state_closing') : t('pos.state_opened');
  return (
    <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
      {label}
    </span>
  );
}

function OpenSessionsTable({ rows }) {
  const { t } = useTranslation();
  const headers = ['branch', 'session', 'cashier', 'opened_at', 'open_for', 'orders', 'type', 'status'];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-100">
            {headers.map((k) => (
              <th key={k} className={clsx(
                'px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap',
                (k === 'orders' || k === 'open_for') ? 'text-end' : 'text-start'
              )}>
                {t(`pos.${k}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.session_id} className={clsx('border-b border-slate-50 transition-colors', SEV_ROW[s.severity] || '')}>
              <td className="px-4 py-3 font-medium text-slate-700" dir="auto">{s.branch}</td>
              <td className="px-4 py-3 text-slate-500 font-mono text-xs whitespace-nowrap">{s.name}</td>
              <td className="px-4 py-3 text-slate-500 text-xs" dir="auto">{s.cashier}</td>
              <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap" style={{ direction: 'ltr' }}>{formatDate(s.start_at)}</td>
              <td className={clsx('px-4 py-3 text-end tabular-nums whitespace-nowrap', SEV_TEXT[s.severity] || '')} style={{ direction: 'ltr' }}>
                {fmtAge(s.age_hours)}
              </td>
              <td className="px-4 py-3 text-end tabular-nums text-slate-600">{(s.order_count ?? 0).toLocaleString()}</td>
              <td className="px-4 py-3">
                {s.rescue
                  ? <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">{t('pos.rescue_badge')}</span>
                  : <span className="text-xs text-slate-400">{t('pos.normal')}</span>}
              </td>
              <td className="px-4 py-3"><StatusPill state={s.state} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PosSessions() {
  const { filters } = useFilters();
  const [applied, setApplied] = useState(filters);
  const { data, isLoading, error } = usePosSessions(applied);
  const { t } = useTranslation();

  const summary = data?.summary ?? {};
  const openSessions = data?.open_sessions ?? [];
  const byBranch = data?.by_branch ?? [];

  const staleCount = (summary.warning_count ?? 0) + (summary.critical_count ?? 0);

  // sessions_count per branch (top 15 for readability) — horizontal bars fit long Arabic names.
  const chartData = byBranch
    .filter((b) => b.sessions_count > 0)
    .slice(0, 15)
    .map((b) => ({ name: b.branch, sessions: b.sessions_count }));

  const BRANCH_COLS = [
    { key: 'branch', header: t('pos.branch'), sortable: true, arabic: true, exportValue: (r) => r.branch },
    { key: 'company', header: t('pos.company'), sortable: true, arabic: true, exportValue: (r) => r.company },
    { key: 'open_now', header: t('pos.open_now_col'), sortable: true, align: 'right',
      render: (r) => <span className={r.open_now > 0 ? 'font-semibold text-rose-600' : 'text-slate-500'}>{r.open_now}</span> },
    { key: 'oldest_open_age_days', header: t('pos.oldest_open_d'), sortable: true, align: 'right',
      render: (r) => (r.oldest_open_age_days ? r.oldest_open_age_days.toFixed(1) : '—') },
    { key: 'sessions_count', header: t('pos.sessions_period'), sortable: true, align: 'right',
      render: (r) => r.sessions_count.toLocaleString() },
    { key: 'sessions_per_active_day', header: t('pos.sessions_per_day'), sortable: true, align: 'right',
      render: (r) => r.sessions_per_active_day.toFixed(2) },
    { key: 'avg_duration_hours', header: t('pos.avg_duration'), sortable: true, align: 'right',
      render: (r) => r.avg_duration_hours.toFixed(1) },
    { key: 'max_duration_hours', header: t('pos.longest'), sortable: true, align: 'right',
      render: (r) => r.max_duration_hours.toFixed(1) },
    { key: 'long_sessions_count', header: t('pos.long_over_24h'), sortable: true, align: 'right' },
    { key: 'discipline', header: t('pos.discipline'), sortable: true, render: (r) => <DisciplinePill flag={r.discipline} /> },
  ];

  return (
    <div className="space-y-6">
      <FilterPanel onApply={setApplied} />

      {/* KPI cards (from summary — live) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title={t('pos.open_now')}
          value={summary.open_now_total?.toLocaleString() ?? '—'}
          icon={DoorOpen}
          color="indigo"
          loading={isLoading}
          subtitle={data?.cached ? t('common.cached') : t('common.live')}
        />
        <KPICard
          title={t('pos.stale')}
          value={staleCount.toLocaleString()}
          icon={AlertTriangle}
          color={staleCount > 0 ? 'rose' : 'emerald'}
          loading={isLoading}
          subtitle={`${summary.critical_count ?? 0} critical · ${summary.warning_count ?? 0} warning`}
        />
        <KPICard
          title={t('pos.oldest_open')}
          value={summary.oldest_open_age_days != null ? Math.round(summary.oldest_open_age_days).toLocaleString() : '—'}
          icon={Clock}
          color="amber"
          loading={isLoading}
        />
        <KPICard
          title={t('pos.rescue')}
          value={summary.rescue_open_count?.toLocaleString() ?? '—'}
          icon={LifeBuoy}
          color="sky"
          loading={isLoading}
        />
      </div>

      <ErrorBanner error={error} />

      {/* Open sessions (live — ignores the date filter) */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2 flex-wrap">
          <DoorOpen className="h-4 w-4 text-indigo-500" />
          <h3 className="font-semibold text-slate-700 text-sm">{t('pos.open_sessions_title')}</h3>
          <span className="text-xs text-slate-400">· {t('pos.open_sessions_note')}</span>
          <span className="ms-auto text-xs text-slate-400">{openSessions.length}</span>
        </div>
        {isLoading
          ? <div className="h-24 animate-pulse bg-slate-50" />
          : openSessions.length > 0
            ? <OpenSessionsTable rows={openSessions} />
            : <EmptyState message={t('pos.empty_open')} />
        }
      </div>

      {/* Sessions per branch (selected period) */}
      {!isLoading && chartData.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('pos.chart_title')}</h2>
          <ResponsiveContainer width="100%" height={Math.max(220, chartData.length * 28)}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 24, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={150} />
              <Tooltip formatter={(v) => v.toLocaleString()} />
              <Bar dataKey="sessions" name={t('pos.sessions_period')} fill="#4f46e5" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Per-branch closing discipline (selected period) */}
      <div>
        <h2 className="text-sm font-semibold text-slate-700 mb-3">{t('pos.by_branch_title')}</h2>
        {isLoading || byBranch.length > 0
          ? <DataTable
              columns={BRANCH_COLS}
              data={byBranch}
              loading={isLoading}
              emptyMessage={t('pos.empty_branch')}
              filename={`pos-sessions-by-branch-${applied.date_from}-${applied.date_to}.csv`}
            />
          : <EmptyState message={t('pos.empty_branch')} />
        }
      </div>
    </div>
  );
}
