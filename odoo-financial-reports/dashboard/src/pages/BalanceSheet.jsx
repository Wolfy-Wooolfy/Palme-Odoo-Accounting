import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Layers, TrendingDown, Minus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useFilters } from '../context/FilterContext';
import { useBalanceSheet } from '../hooks/useReports';
import KPICard from '../components/KPICard';
import DataTable from '../components/DataTable';
import EmptyState from '../components/EmptyState';
import { formatCurrency, formatCompact } from '../utils/formatters';

function Section({ title, data, total, loading, icon: Icon, color, filename, emptyMsg }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 text-${color}-500`} />
          <h3 className="font-semibold text-slate-700 text-sm">{title}</h3>
        </div>
        <span className={`text-sm font-bold tabular-nums text-${color}-700`}>{formatCompact(total)}</span>
      </div>
      {loading || (data?.length ?? 0) > 0
        ? <DataTable columns={[]} data={data ?? []} loading={loading} filename={filename} />
        : <EmptyState message={emptyMsg} />
      }
    </div>
  );
}

export default function BalanceSheet() {
  const { filters } = useFilters();
  const [asOf, setAsOf] = useState(filters.date_to);
  const [pendingAsOf, setPendingAsOf] = useState(filters.date_to);
  const { t } = useTranslation();

  const bsFilters = { date_from: asOf, date_to: asOf, company_id: filters.company_id, posted_only: filters.posted_only };
  const { data, isLoading, error } = useBalanceSheet(bsFilters);

  const bs = data ?? {};
  // balance_check = assets + liabilities + equity in raw debit-credit model (should be 0 when balanced)
  // The synthetic "Current Period Earnings" row in equity makes this approach to 0 after the BS fix.
  const diff = Math.abs(bs.balance_check ?? (
    (bs.assets?.total ?? 0) + (bs.liabilities?.total ?? 0) + (bs.equity?.total ?? 0)
  ));
  const balanced = diff < 1;
  // For KPI display: show abs value so it's comparable with assets total
  const liabEquityDisplay = Math.abs((bs.liabilities?.total ?? 0) + (bs.equity?.total ?? 0));

  const BS_COLS = [
    { key: 'code', header: t('balance_sheet.code'), sortable: true, width: '110px', exportValue: (r) => r.code },
    { key: 'name', header: t('balance_sheet.account'), sortable: true, arabic: true, exportValue: (r) => r.name },
    { key: 'account_type', header: t('balance_sheet.type'), sortable: true, width: '160px', exportValue: (r) => r.account_type },
    { key: 'balance', header: t('balance_sheet.balance'), sortable: true, align: 'right', type: 'currency', colored: true, exportValue: (r) => r.balance },
  ];

  return (
    <div className="space-y-6">
      {/* As-of date selector */}
      <div className="bg-white border border-slate-200 rounded-xl px-5 py-4">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="text-xs font-medium text-slate-500 block mb-1">{t('balance_sheet.as_of_date')}</label>
            <input
              type="date"
              value={pendingAsOf}
              onChange={(e) => setPendingAsOf(e.target.value)}
              className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-300"
              style={{ direction: 'ltr' }}
            />
          </div>
          <button
            onClick={() => setAsOf(pendingAsOf)}
            className="px-6 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors"
          >
            {t('common.apply')}
          </button>
          <p className="text-xs text-slate-400 self-center">{t('filters.cumulative_note')}</p>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title={t('kpi.total_assets')} value={formatCompact(bs.assets?.total)} icon={Layers} color="indigo" loading={isLoading} />
        <KPICard title={t('kpi.total_liabilities')} value={formatCompact(bs.liabilities?.total)} icon={TrendingDown} color="rose" loading={isLoading} />
        <KPICard title={t('kpi.total_equity')} value={formatCompact(bs.equity?.total)} icon={Minus} color="emerald" loading={isLoading} />
        <KPICard
          title={t('kpi.liab_equity')}
          value={formatCompact(liabEquityDisplay || undefined)}
          color={balanced ? 'emerald' : 'rose'}
          loading={isLoading}
          subtitle={data?.cached ? t('common.cached') : t('common.live')}
        />
      </div>

      {/* Balance check — Bug 2 fix: show exact diff amount */}
      {!isLoading && data && (
        <div className={`flex items-start gap-3 rounded-xl p-4 border ${balanced ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'}`}>
          {balanced
            ? <CheckCircle2 className="h-5 w-5 text-emerald-600 flex-shrink-0 mt-0.5" />
            : <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />}
          <div>
            <p className={`text-sm font-semibold ${balanced ? 'text-emerald-800' : 'text-amber-800'}`}>
              {balanced
                ? t('balance_sheet.balanced_msg')
                : t('balance_sheet.imbalanced_msg', { amount: formatCurrency(diff) })}
            </p>
            {!balanced && (
              <p className="text-xs text-amber-700 mt-1">
                {t('balance_sheet.imbalance_explanation')}
              </p>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">
          {error.response?.data?.detail || error.message}
        </div>
      )}

      {/* Three sections */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-indigo-500" />
            <h3 className="font-semibold text-slate-700 text-sm">{t('balance_sheet.assets')}</h3>
          </div>
          <span className="text-sm font-bold tabular-nums text-indigo-700">{formatCompact(bs.assets?.total)}</span>
        </div>
        {isLoading || (bs.assets?.accounts?.length ?? 0) > 0
          ? <DataTable columns={BS_COLS} data={bs.assets?.accounts ?? []} loading={isLoading} filename={`bs-assets-${asOf}.csv`} />
          : <EmptyState message={t('balance_sheet.no_assets')} />
        }
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingDown className="h-4 w-4 text-rose-500" />
            <h3 className="font-semibold text-slate-700 text-sm">{t('balance_sheet.liabilities')}</h3>
          </div>
          <span className="text-sm font-bold tabular-nums text-rose-700">{formatCompact(bs.liabilities?.total)}</span>
        </div>
        {isLoading || (bs.liabilities?.accounts?.length ?? 0) > 0
          ? <DataTable columns={BS_COLS} data={bs.liabilities?.accounts ?? []} loading={isLoading} filename={`bs-liabilities-${asOf}.csv`} />
          : <EmptyState message={t('balance_sheet.no_liabilities')} />
        }
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Minus className="h-4 w-4 text-emerald-500" />
            <h3 className="font-semibold text-slate-700 text-sm">{t('balance_sheet.equity')}</h3>
          </div>
          <span className="text-sm font-bold tabular-nums text-emerald-700">{formatCompact(bs.equity?.total)}</span>
        </div>
        {isLoading || (bs.equity?.accounts?.length ?? 0) > 0
          ? <DataTable columns={BS_COLS} data={bs.equity?.accounts ?? []} loading={isLoading} filename={`bs-equity-${asOf}.csv`} />
          : <EmptyState message={t('balance_sheet.no_equity')} />
        }
      </div>
    </div>
  );
}
