import { useState } from 'react';
import { ShoppingCart, TrendingUp, DollarSign, BarChart2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { useFilters } from '../context/FilterContext';
import { useSales } from '../hooks/useReports';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import DataTable from '../components/DataTable';
import EmptyState from '../components/EmptyState';
import ErrorBanner from '../components/ErrorBanner';
import { formatCurrency, formatCompact, formatAxisCurrency } from '../utils/formatters';

export default function SalesReport() {
  const { filters } = useFilters();
  const [applied, setApplied] = useState(filters);
  const { data, isLoading, error } = useSales(applied);
  const { t } = useTranslation();

  const summary = data?.summary ?? {};
  const topCustomers = data?.top_customers ?? [];
  const monthlyTrend = data?.monthly_trend ?? [];

  const CUSTOMER_COLS = [
    { key: 'partner_name', header: t('sales.partner'), sortable: true, arabic: true, exportValue: (r) => r.partner_name },
    { key: 'order_count', header: t('sales.order_count'), sortable: true, align: 'right', exportValue: (r) => r.order_count },
    { key: 'total_sales', header: t('sales.amount'), sortable: true, align: 'right', type: 'currency', exportValue: (r) => r.total_sales },
  ];

  return (
    <div className="space-y-6">
      <FilterPanel onApply={setApplied} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title={t('sales.total_orders')} value={summary.total_orders?.toLocaleString()} icon={ShoppingCart} color="indigo" loading={isLoading} />
        <KPICard title={t('sales.total_untaxed')} value={formatCompact(summary.total_untaxed)} icon={TrendingUp} color="emerald" loading={isLoading} />
        <KPICard title={t('sales.total_with_tax')} value={formatCompact(summary.total_with_tax)} icon={DollarSign} color="sky" loading={isLoading} />
        <KPICard title={t('sales.avg_order')} value={formatCompact(summary.average_order_value)} icon={BarChart2} color="amber" loading={isLoading}
          subtitle={data?.cached ? t('common.cached') : t('common.live')} />
      </div>

      <ErrorBanner error={error} />

      {/* Monthly trend */}
      {!isLoading && monthlyTrend.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('sales.monthly_trend')}</h2>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={monthlyTrend} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={50} />
              <YAxis tickFormatter={formatAxisCurrency} tick={{ fontSize: 11 }} width={70} />
              <Tooltip formatter={(v) => formatCurrency(v)} />
              <Line type="monotone" dataKey="amount" name={t('sales.amount')} stroke="#4f46e5" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Top customers */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-700">{t('sales.top_customers')}</h2>
          <span className="text-sm font-bold text-indigo-700 tabular-nums">{formatCompact(summary.total_with_tax)}</span>
        </div>
        {isLoading || topCustomers.length > 0
          ? <DataTable columns={CUSTOMER_COLS} data={topCustomers} loading={isLoading}
              filename={`sales-top-customers-${applied.date_from}-${applied.date_to}.csv`} />
          : <EmptyState message={t('sales.empty')} />
        }
      </div>
    </div>
  );
}
