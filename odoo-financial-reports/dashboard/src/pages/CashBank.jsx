import { useState } from 'react';
import { Landmark, TrendingUp, TrendingDown, ArrowUpDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { useFilters } from '../context/FilterContext';
import { useCashBank } from '../hooks/useReports';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import EmptyState from '../components/EmptyState';
import ErrorBanner from '../components/ErrorBanner';
import { formatCurrency, formatCompact, formatAxisCurrency } from '../utils/formatters';
import clsx from 'clsx';

const PIE_COLORS = [
  '#4f46e5','#10b981','#f43f5e','#f59e0b','#06b6d4',
  '#8b5cf6','#ec4899','#14b8a6','#84cc16','#fb923c',
];

function JournalTable({ journals, loading }) {
  const { t } = useTranslation();
  if (!loading && journals.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-100">
            {['cash_bank.journal','cash_bank.code','cash_bank.company',
              'cash_bank.ending_balance','cash_bank.period_inflow',
              'cash_bank.period_outflow','cash_bank.period_net'].map((k, i) => (
              <th key={k} className={clsx(
                'px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide',
                i >= 3 ? 'text-end' : 'text-start'
              )}>
                {t(k)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {journals.map((j) => (
            <tr key={j.journal_id} className="border-b border-slate-50 hover:bg-slate-50/60">
              <td className="px-4 py-3 font-medium text-slate-700">{j.journal_name}</td>
              <td className="px-4 py-3 text-slate-500 font-mono text-xs">{j.journal_code}</td>
              <td className="px-4 py-3 text-slate-500 text-xs">{j.company}</td>
              <td className={clsx(
                'px-4 py-3 text-end tabular-nums font-medium',
                j.ending_balance >= 0 ? 'text-emerald-700' : 'text-rose-600'
              )}>
                {formatCurrency(j.ending_balance)}
              </td>
              <td className="px-4 py-3 text-end tabular-nums text-emerald-700">{formatCurrency(j.period_inflow)}</td>
              <td className="px-4 py-3 text-end tabular-nums text-rose-600">{formatCurrency(j.period_outflow)}</td>
              <td className={clsx(
                'px-4 py-3 text-end tabular-nums font-medium',
                j.period_net >= 0 ? 'text-emerald-700' : 'text-rose-600'
              )}>
                {formatCurrency(j.period_net)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CashBank() {
  const { filters } = useFilters();
  const [applied, setApplied] = useState(filters);
  const { data, isLoading, error } = useCashBank(applied);
  const { t } = useTranslation();

  const journals = data?.journals ?? [];
  const totals = data?.totals;
  const bankJournals = journals.filter((j) => j.journal_type === 'bank');
  const cashJournals = journals.filter((j) => j.journal_type === 'cash');

  const pieData = journals
    .filter((j) => j.ending_balance > 0)
    .map((j, i) => ({ name: j.journal_name, value: j.ending_balance, fill: PIE_COLORS[i % PIE_COLORS.length] }));

  return (
    <div className="space-y-6">
      <FilterPanel onApply={setApplied} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title={t('cash_bank.ending_balance')} value={formatCompact(totals?.ending_balance)} icon={Landmark} color="indigo" loading={isLoading} />
        <KPICard title={t('cash_bank.period_inflow')} value={formatCompact(totals?.period_inflow)} icon={TrendingUp} color="emerald" loading={isLoading} />
        <KPICard title={t('cash_bank.period_outflow')} value={formatCompact(totals?.period_outflow)} icon={TrendingDown} color="rose" loading={isLoading} />
        <KPICard
          title={t('cash_bank.period_net')}
          value={formatCompact(totals?.period_net)}
          icon={ArrowUpDown}
          color={(totals?.period_net ?? 0) >= 0 ? 'emerald' : 'rose'}
          loading={isLoading}
          subtitle={`${totals?.bank_count ?? 0} banks · ${totals?.cash_count ?? 0} cash`}
        />
      </div>

      <ErrorBanner error={error} />

      {/* Pie chart */}
      {!isLoading && pieData.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('cash_bank.distribution')}</h2>
          <div className="flex flex-wrap items-center gap-6">
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} dataKey="value">
                  {pieData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                </Pie>
                <Tooltip formatter={(v) => formatCurrency(v)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-2 flex-1">
              {pieData.map((e, i) => (
                <div key={e.name} className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div className="h-2.5 w-2.5 rounded-full flex-shrink-0" style={{ background: e.fill }} />
                    <span className="text-xs text-slate-600 truncate">{e.name}</span>
                  </div>
                  <span className="text-xs tabular-nums font-medium text-slate-800">{formatCompact(e.value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Bank journals */}
      {(isLoading || bankJournals.length > 0) && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <Landmark className="h-4 w-4 text-indigo-500" />
            <h3 className="font-semibold text-slate-700 text-sm">{t('cash_bank.bank_journals')}</h3>
            <span className="ms-auto text-xs text-slate-400">{bankJournals.length}</span>
          </div>
          {isLoading
            ? <div className="h-24 animate-pulse bg-slate-50" />
            : <JournalTable journals={bankJournals} />
          }
        </div>
      )}

      {/* Cash journals */}
      {(isLoading || cashJournals.length > 0) && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            <h3 className="font-semibold text-slate-700 text-sm">{t('cash_bank.cash_journals')}</h3>
            <span className="ms-auto text-xs text-slate-400">{cashJournals.length}</span>
          </div>
          {isLoading
            ? <div className="h-24 animate-pulse bg-slate-50" />
            : <JournalTable journals={cashJournals} />
          }
        </div>
      )}

      {!isLoading && journals.length === 0 && <EmptyState message={t('cash_bank.empty')} />}
    </div>
  );
}
