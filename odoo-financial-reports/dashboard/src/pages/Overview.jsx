import { useQueries } from '@tanstack/react-query';
import { TrendingUp, TrendingDown, DollarSign, Layers } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import { useTranslation } from 'react-i18next';
import { fetchProfitLoss, fetchBalanceSheet } from '../api/reports';
import { useFilters } from '../context/FilterContext';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import { formatCompact, formatCurrency, formatAxisCurrency, formatPercent } from '../utils/formatters';

const PIE_COLORS = ['#4f46e5', '#f43f5e', '#10b981'];

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg p-3 text-sm">
      <p className="font-medium text-slate-700 mb-1">{label || payload[0]?.name}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color }} className="tabular-nums">
          {formatCurrency(p.value)}
        </p>
      ))}
    </div>
  );
};

export default function Overview() {
  const { filters } = useFilters();
  const { t } = useTranslation();

  const bsFilters = { date_from: filters.date_to, date_to: filters.date_to, company_id: filters.company_id, posted_only: filters.posted_only };

  const [plQ, bsQ] = useQueries({
    queries: [
      { queryKey: ['profit-loss', filters], queryFn: () => fetchProfitLoss(filters), staleTime: 5 * 60_000 },
      { queryKey: ['balance-sheet', bsFilters], queryFn: () => fetchBalanceSheet(bsFilters), staleTime: 5 * 60_000 },
    ],
  });

  const pl = plQ.data;
  const bs = bsQ.data;
  const loading = plQ.isLoading || bsQ.isLoading;
  const margin = pl?.revenue?.total > 0 ? pl.net_profit / pl.revenue.total : null;

  const rvExp = [
    { name: t('charts.assets') === 'Assets' ? 'Revenue' : t('kpi.revenue'), value: pl?.revenue?.total ?? 0, fill: '#10b981' },
    { name: t('kpi.expenses'), value: pl?.expenses?.total ?? 0, fill: '#f43f5e' },
  ];

  // Bug 1 fix: show code + truncated name
  const top5Revenue = (pl?.revenue?.accounts ?? []).slice(0, 5).map((a) => ({
    name: `${a.code} - ${a.name.substring(0, 30)}${a.name.length > 30 ? '…' : ''}`,
    fullName: a.name,
    value: a.amount,
  }));

  const bsPie = bs
    ? [
        { name: t('charts.assets'), value: Math.abs(bs.assets.total) },
        { name: t('charts.liabilities'), value: Math.abs(bs.liabilities.total) },
        { name: t('charts.equity'), value: Math.abs(bs.equity.total) },
      ]
    : [];

  return (
    <div className="space-y-6">
      <FilterPanel />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title={t('kpi.revenue')}
          value={formatCompact(pl?.revenue?.total)}
          icon={TrendingUp}
          color="emerald"
          loading={plQ.isLoading}
          subtitle={t('kpi.accounts', { count: pl?.revenue?.accounts?.length ?? 0 })}
        />
        <KPICard
          title={t('kpi.expenses')}
          value={formatCompact(pl?.expenses?.total)}
          icon={TrendingDown}
          color="rose"
          loading={plQ.isLoading}
          subtitle={t('kpi.accounts', { count: pl?.expenses?.accounts?.length ?? 0 })}
        />
        <KPICard
          title={t('kpi.net_profit')}
          value={formatCompact(pl?.net_profit)}
          icon={DollarSign}
          color={pl?.net_profit >= 0 ? 'emerald' : 'rose'}
          loading={plQ.isLoading}
          subtitle={margin !== null ? formatPercent(margin) : undefined}
        />
        <KPICard
          title={t('kpi.total_assets')}
          value={formatCompact(bs?.assets?.total)}
          icon={Layers}
          color="indigo"
          loading={bsQ.isLoading}
          subtitle={t('kpi.as_of', { date: filters.date_to })}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Revenue vs Expenses */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('charts.revenue_vs_expenses')}</h2>
          {loading ? (
            <div className="h-48 bg-slate-50 rounded-lg animate-pulse" />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={rvExp} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={formatAxisCurrency} tick={{ fontSize: 11 }} width={60} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {rvExp.map((e, i) => <Cell key={i} fill={e.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Top 5 Revenue */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('charts.top_revenue')}</h2>
          {plQ.isLoading ? (
            <div className="h-48 bg-slate-50 rounded-lg animate-pulse" />
          ) : top5Revenue.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-slate-400 text-sm">{t('charts.no_revenue')}</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={top5Revenue} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 120 }}>
                <XAxis type="number" tickFormatter={formatAxisCurrency} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={115} />
                <Tooltip formatter={(v, n, p) => [formatCurrency(v), p.payload.fullName]} />
                <Bar dataKey="value" fill="#10b981" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Balance Sheet Pie */}
      {bsPie.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">
            {t('charts.balance_sheet_breakdown')} · {t('kpi.as_of', { date: filters.date_to })}
          </h2>
          <div className="flex items-center gap-8">
            <ResponsiveContainer width={240} height={200}>
              <PieChart>
                <Pie data={bsPie} cx="50%" cy="50%" innerRadius={60} outerRadius={90} dataKey="value">
                  {bsPie.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} />)}
                </Pie>
                <Legend />
                <Tooltip formatter={(v) => formatCurrency(v)} />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-3 flex-1">
              {bsPie.map((entry, i) => (
                <div key={entry.name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full" style={{ background: PIE_COLORS[i] }} />
                    <span className="text-sm text-slate-600">{entry.name}</span>
                  </div>
                  <span className="text-sm font-medium tabular-nums text-slate-800">{formatCompact(entry.value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
