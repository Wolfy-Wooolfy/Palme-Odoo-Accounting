import { useState } from 'react';
import { TrendingUp, TrendingDown, DollarSign, Percent } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { useTranslation } from 'react-i18next';
import { useFilters } from '../context/FilterContext';
import { useProfitLoss } from '../hooks/useReports';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import DataTable from '../components/DataTable';
import EmptyState from '../components/EmptyState';
import ErrorBanner from '../components/ErrorBanner';
import { formatCurrency, formatCompact, formatPercent, formatAxisCurrency } from '../utils/formatters';

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow p-3 text-sm max-w-xs">
      <p className="font-medium text-slate-700 mb-1 truncate">{payload[0]?.payload?.fullName || payload[0]?.payload?.name}</p>
      <p className="tabular-nums" style={{ color: payload[0]?.fill }}>{formatCurrency(payload[0]?.value)}</p>
    </div>
  );
};

export default function ProfitLoss() {
  const { filters } = useFilters();
  const [applied, setApplied] = useState(filters);
  const { data, isLoading, error } = useProfitLoss(applied);
  const { t } = useTranslation();

  const pl = data ?? {};
  const margin = pl.revenue?.total > 0 ? pl.net_profit / pl.revenue.total : null;

  const ACC_COLS = (type) => [
    { key: 'code', header: t('balance_sheet.code'), sortable: true, width: '100px', exportValue: (r) => r.code },
    { key: 'name', header: t('balance_sheet.account'), sortable: true, arabic: true, exportValue: (r) => r.name },
    {
      key: 'amount',
      header: type === 'revenue' ? t('kpi.revenue') : t('kpi.expenses'),
      sortable: true,
      align: 'right',
      type: 'currency',
      exportValue: (r) => r.amount,
    },
  ];

  const top10 = [
    ...(pl.revenue?.accounts ?? []).slice(0, 5).map((a) => ({
      name: (a.code || '').slice(0, 12),
      fullName: a.name,
      revenue: a.amount,
      expense: 0,
    })),
    ...(pl.expenses?.accounts ?? []).slice(0, 5).map((a) => ({
      name: (a.code || '').slice(0, 12),
      fullName: a.name,
      revenue: 0,
      expense: a.amount,
    })),
  ];

  return (
    <div className="space-y-6">
      <FilterPanel onApply={setApplied} />

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title={t('profit_loss.total_revenue')} value={formatCompact(pl.revenue?.total)} icon={TrendingUp} color="emerald" loading={isLoading} />
        <KPICard title={t('profit_loss.total_expenses')} value={formatCompact(pl.expenses?.total)} icon={TrendingDown} color="rose" loading={isLoading} />
        <KPICard
          title={t('profit_loss.net_profit')}
          value={formatCompact(pl.net_profit)}
          icon={DollarSign}
          color={(pl.net_profit ?? 0) >= 0 ? 'emerald' : 'rose'}
          loading={isLoading}
        />
        <KPICard
          title={t('profit_loss.profit_margin')}
          value={margin !== null ? formatPercent(margin) : '—'}
          icon={Percent}
          color={(margin ?? 0) >= 0.1 ? 'emerald' : 'amber'}
          loading={isLoading}
          subtitle={data?.cached ? t('common.cached') : t('common.live')}
        />
      </div>

      <ErrorBanner error={error} />

      {/* Top accounts chart */}
      {!isLoading && top10.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('profit_loss.top_accounts')}</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={top10} margin={{ top: 5, right: 10, bottom: 20, left: 20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
              <YAxis tickFormatter={formatAxisCurrency} tick={{ fontSize: 11 }} width={60} />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <Bar dataKey="revenue" name={t('kpi.revenue')} fill="#10b981" radius={[4,4,0,0]} />
              <Bar dataKey="expense" name={t('kpi.expenses')} fill="#f43f5e" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Two-column tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-700">{t('profit_loss.revenue_section')}</h2>
            <span className="text-sm font-bold text-emerald-700 tabular-nums">{formatCompact(pl.revenue?.total)}</span>
          </div>
          {isLoading || (pl.revenue?.accounts ?? []).length > 0
            ? <DataTable columns={ACC_COLS('revenue')} data={pl.revenue?.accounts ?? []} loading={isLoading}
                filename={`pl-revenue-${applied.date_from}-${applied.date_to}.csv`} />
            : <EmptyState message={t('profit_loss.no_revenue')} />
          }
        </div>
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-700">{t('profit_loss.expenses_section')}</h2>
            <span className="text-sm font-bold text-rose-600 tabular-nums">{formatCompact(pl.expenses?.total)}</span>
          </div>
          {isLoading || (pl.expenses?.accounts ?? []).length > 0
            ? <DataTable columns={ACC_COLS('expense')} data={pl.expenses?.accounts ?? []} loading={isLoading}
                filename={`pl-expenses-${applied.date_from}-${applied.date_to}.csv`} />
            : <EmptyState message={t('profit_loss.no_expenses')} />
          }
        </div>
      </div>
    </div>
  );
}
