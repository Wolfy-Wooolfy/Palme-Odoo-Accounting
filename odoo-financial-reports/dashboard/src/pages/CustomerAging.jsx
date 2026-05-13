import { useState } from 'react';
import { Users, AlertCircle, Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { useFilters } from '../context/FilterContext';
import { useCustomerAging } from '../hooks/useReports';
import KPICard from '../components/KPICard';
import DataTable from '../components/DataTable';
import EmptyState from '../components/EmptyState';
import { formatCurrency, formatCompact, formatAxisCurrency } from '../utils/formatters';

const BUCKET_COLORS = ['#10b981','#84cc16','#f59e0b','#f97316','#ef4444','#991b1b'];
const BUCKETS = ['not_due','1_30','31_60','61_90','91_180','over_180'];

export default function CustomerAging() {
  const { filters } = useFilters();
  const { t } = useTranslation();
  const [asOf, setAsOf] = useState(filters.date_to);
  const [pending, setPending] = useState(filters.date_to);

  const agingFilters = {
    date_to: asOf,
    company_id: filters.company_id,
    posted_only: filters.posted_only,
  };

  const { data, isLoading, error } = useCustomerAging(agingFilters);
  const totals = data?.totals ?? {};
  const partners = data?.partners ?? [];

  const chartData = BUCKETS.map((k, i) => ({
    name: t(`aging.${k}`),
    value: totals[k] ?? 0,
    fill: BUCKET_COLORS[i],
  })).filter((d) => d.value > 0);

  const COLUMNS = [
    { key: 'partner_name', header: t('aging.partner'), sortable: true, arabic: true, exportValue: (r) => r.partner_name },
    ...BUCKETS.map((k) => ({
      key: k,
      header: t(`aging.${k}`),
      sortable: true,
      align: 'right',
      type: 'currency',
      exportValue: (r) => r[k],
    })),
    { key: 'total', header: t('aging.total'), sortable: true, align: 'right', type: 'currency', colored: true, exportValue: (r) => r.total },
  ];

  return (
    <div className="space-y-6">
      <div className="bg-white border border-slate-200 rounded-xl px-5 py-4">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="text-xs font-medium text-slate-500 block mb-1">{t('aging.as_of')}</label>
            <input
              type="date"
              value={pending}
              onChange={(e) => setPending(e.target.value)}
              className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-300"
              style={{ direction: 'ltr' }}
            />
          </div>
          <button
            onClick={() => setAsOf(pending)}
            className="px-6 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors"
          >
            {t('common.apply')}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <KPICard title={t('aging.grand_total')} value={formatCompact(data?.grand_total)} icon={Users} color="indigo" loading={isLoading} />
        <KPICard title={t('aging.overdue_total')} value={formatCompact(data?.overdue_total)} icon={AlertCircle}
          color={(data?.overdue_total ?? 0) > 0 ? 'rose' : 'emerald'} loading={isLoading} />
        <KPICard title={t('aging.partner_count')} value={data?.partner_count?.toLocaleString()} icon={Clock} color="sky" loading={isLoading} />
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">
          {error.response?.data?.detail || error.message}
        </div>
      )}

      {!isLoading && chartData.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('aging.distribution')}</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={formatAxisCurrency} tick={{ fontSize: 11 }} width={70} />
              <Tooltip formatter={(v) => formatCurrency(v)} />
              <Bar dataKey="value" radius={[4,4,0,0]}>
                {chartData.map((e, i) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {!isLoading && partners.length === 0 && <EmptyState message={t('aging.empty')} />}
      {(isLoading || partners.length > 0) && (
        <DataTable columns={COLUMNS} data={partners} loading={isLoading}
          filename={`customer-aging-${asOf}.csv`} />
      )}
    </div>
  );
}
