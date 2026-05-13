import { useState } from 'react';
import { Package, TrendingDown, DollarSign, BarChart2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { useFilters } from '../context/FilterContext';
import { usePurchases } from '../hooks/useReports';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import DataTable from '../components/DataTable';
import EmptyState from '../components/EmptyState';
import ErrorBanner from '../components/ErrorBanner';
import { formatCurrency, formatCompact, formatAxisCurrency } from '../utils/formatters';

export default function PurchaseReport() {
  const { filters } = useFilters();
  const [applied, setApplied] = useState(filters);
  const { data, isLoading, error } = usePurchases(applied);
  const { t } = useTranslation();

  const summary = data?.summary ?? {};
  const topVendors = data?.top_vendors ?? [];
  const monthlyTrend = data?.monthly_trend ?? [];

  const VENDOR_COLS = [
    { key: 'partner_name', header: t('purchases.partner'), sortable: true, arabic: true, exportValue: (r) => r.partner_name },
    { key: 'order_count', header: t('purchases.order_count'), sortable: true, align: 'right', exportValue: (r) => r.order_count },
    { key: 'total_purchases', header: t('purchases.amount'), sortable: true, align: 'right', type: 'currency', exportValue: (r) => r.total_purchases },
  ];

  return (
    <div className="space-y-6">
      <FilterPanel onApply={setApplied} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title={t('purchases.total_orders')} value={summary.total_orders?.toLocaleString()} icon={Package} color="indigo" loading={isLoading} />
        <KPICard title={t('purchases.total_untaxed')} value={formatCompact(summary.total_untaxed)} icon={TrendingDown} color="rose" loading={isLoading} />
        <KPICard title={t('purchases.total_with_tax')} value={formatCompact(summary.total_with_tax)} icon={DollarSign} color="sky" loading={isLoading} />
        <KPICard title={t('purchases.avg_order')} value={formatCompact(summary.average_order_value)} icon={BarChart2} color="amber" loading={isLoading}
          subtitle={data?.cached ? t('common.cached') : t('common.live')} />
      </div>

      <ErrorBanner error={error} />

      {!isLoading && monthlyTrend.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('purchases.monthly_trend')}</h2>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={monthlyTrend} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={50} />
              <YAxis tickFormatter={formatAxisCurrency} tick={{ fontSize: 11 }} width={70} />
              <Tooltip formatter={(v) => formatCurrency(v)} />
              <Line type="monotone" dataKey="amount" name={t('purchases.amount')} stroke="#f43f5e" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-700">{t('purchases.top_vendors')}</h2>
          <span className="text-sm font-bold text-rose-600 tabular-nums">{formatCompact(summary.total_with_tax)}</span>
        </div>
        {isLoading || topVendors.length > 0
          ? <DataTable columns={VENDOR_COLS} data={topVendors} loading={isLoading}
              filename={`purchases-top-vendors-${applied.date_from}-${applied.date_to}.csv`} />
          : <EmptyState message={t('purchases.empty')} />
        }
      </div>
    </div>
  );
}
