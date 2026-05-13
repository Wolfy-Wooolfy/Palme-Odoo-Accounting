import { useState } from 'react';
import { Scale, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useFilters } from '../context/FilterContext';
import { useTrialBalance } from '../hooks/useReports';
import FilterPanel from '../components/FilterPanel';
import KPICard from '../components/KPICard';
import DataTable from '../components/DataTable';
import ErrorBanner from '../components/ErrorBanner';
import { formatCurrency, formatCompact } from '../utils/formatters';

export default function TrialBalance() {
  const { filters } = useFilters();
  const [applied, setApplied] = useState(filters);
  const { data, isLoading, error } = useTrialBalance(applied);
  const { t } = useTranslation();

  const rows = data?.rows ?? [];
  const totals = data?.totals;
  const diff = totals ? Math.abs(totals.debit - totals.credit) : null;
  const balanced = diff !== null && diff < 1;

  const COLUMNS = [
    { key: 'code', header: t('trial_balance.code'), sortable: true, width: '110px', exportValue: (r) => r.code },
    { key: 'name', header: t('trial_balance.account'), sortable: true, arabic: true, exportValue: (r) => r.name },
    { key: 'account_type', header: t('trial_balance.type'), sortable: true, width: '160px', exportValue: (r) => r.account_type },
    { key: 'debit', header: t('trial_balance.debit'), sortable: true, align: 'right', type: 'currency', exportValue: (r) => r.debit },
    { key: 'credit', header: t('trial_balance.credit'), sortable: true, align: 'right', type: 'currency', exportValue: (r) => r.credit },
    { key: 'balance', header: t('trial_balance.balance'), sortable: true, align: 'right', type: 'currency', colored: true, exportValue: (r) => r.balance },
  ];

  return (
    <div className="space-y-6">
      <FilterPanel onApply={setApplied} />

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title={t('trial_balance.total_debit')} value={formatCompact(totals?.debit)} icon={Scale} color="indigo" loading={isLoading} />
        <KPICard title={t('trial_balance.total_credit')} value={formatCompact(totals?.credit)} icon={Scale} color="indigo" loading={isLoading} />
        <KPICard
          title={t('trial_balance.net_balance')}
          value={formatCompact(totals?.balance)}
          color={Math.abs(totals?.balance ?? 0) < 1 ? 'emerald' : 'rose'}
          loading={isLoading}
        />
        <KPICard
          title={t('trial_balance.accounts_count')}
          value={data?.row_count?.toLocaleString()}
          color="sky"
          loading={isLoading}
          subtitle={data?.cached ? t('common.cached') : t('common.live')}
        />
      </div>

      {/* Balance check */}
      {!isLoading && totals && (
        <div className={`flex items-center gap-3 rounded-xl p-4 border ${balanced ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'}`}>
          {balanced
            ? <CheckCircle2 className="h-5 w-5 text-emerald-600 flex-shrink-0" />
            : <AlertCircle className="h-5 w-5 text-rose-600 flex-shrink-0" />}
          <p className={`text-sm font-medium ${balanced ? 'text-emerald-800' : 'text-rose-800'}`}>
            {balanced
              ? t('trial_balance.balanced_msg')
              : t('trial_balance.imbalanced_msg', { amount: formatCurrency(diff) })}
          </p>
        </div>
      )}

      <ErrorBanner error={error} />

      <DataTable
        columns={COLUMNS}
        data={rows}
        loading={isLoading}
        filename={`trial-balance-${applied.date_from}-${applied.date_to}.csv`}
        emptyMessage={t('trial_balance.empty')}
      />
    </div>
  );
}
