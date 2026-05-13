import { useState } from 'react';
import { AlertTriangle, AlertCircle, Info, CheckCircle2, ChevronDown, ChevronUp, Stethoscope } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useFilters } from '../context/FilterContext';
import { useDiagnostic } from '../hooks/useReports';
import KPICard from '../components/KPICard';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';
import { formatCurrency, formatCompact } from '../utils/formatters';

function SeverityIcon({ severity }) {
  if (severity === 'critical') return <AlertCircle className="h-4 w-4 text-red-600 flex-shrink-0 mt-0.5" />;
  if (severity === 'high') return <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0 mt-0.5" />;
  return <Info className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />;
}

const SEVERITY_STYLES = {
  critical: 'bg-red-50 border-red-200 text-red-900',
  high: 'bg-amber-50 border-amber-200 text-amber-900',
  info: 'bg-blue-50 border-blue-200 text-blue-900',
};

function IssueCard({ issue }) {
  const [expanded, setExpanded] = useState(issue.severity === 'critical');
  const { t } = useTranslation();
  const cls = SEVERITY_STYLES[issue.severity] || SEVERITY_STYLES.info;

  const severityLabel = {
    critical: t('diagnostics.severity_critical'),
    high: t('diagnostics.severity_high'),
    info: t('diagnostics.severity_info'),
  }[issue.severity] || issue.severity;

  return (
    <div className={`border rounded-xl overflow-hidden ${cls}`}>
      <button
        className="w-full flex items-start gap-3 p-4 text-start"
        onClick={() => setExpanded((e) => !e)}
      >
        <SeverityIcon severity={issue.severity} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-xs font-bold uppercase tracking-wide opacity-70">{severityLabel}</span>
            <span className="text-xs opacity-60">· {issue.type}</span>
          </div>
          <p className="text-sm font-medium">{issue.message}</p>
        </div>
        {expanded
          ? <ChevronUp className="h-4 w-4 flex-shrink-0 mt-0.5 opacity-60" />
          : <ChevronDown className="h-4 w-4 flex-shrink-0 mt-0.5 opacity-60" />}
      </button>

      {expanded && (
        <div className="border-t border-current/10 px-4 pb-4 pt-3 space-y-2">
          {issue.note && <p className="text-xs opacity-75">{issue.note}</p>}
          {issue.recommendation && (
            <p className="text-xs font-medium bg-white/50 rounded-lg p-3">{issue.recommendation}</p>
          )}
          {issue.types && (
            <div>
              <p className="text-xs font-semibold mb-1">{t('diagnostics.types_list')}:</p>
              <div className="flex flex-wrap gap-1">
                {issue.types.map((tp) => (
                  <span key={tp} className="text-xs font-mono bg-white/60 rounded px-2 py-0.5">{tp}</span>
                ))}
              </div>
            </div>
          )}
          {issue.accounts && issue.accounts.length > 0 && (
            <div>
              <p className="text-xs font-semibold mb-1">{t('diagnostics.accounts_list')} (top 10):</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="opacity-60">
                      <th className="text-start py-1 pe-3">Code</th>
                      <th className="text-start py-1 pe-3">Name</th>
                      <th className="text-start py-1 pe-3">Type</th>
                      <th className="text-end py-1">Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {issue.accounts.slice(0, 10).map((a, i) => (
                      <tr key={i} className="border-t border-current/10">
                        <td className="py-1 pe-3 font-mono">{a.code}</td>
                        <td className="py-1 pe-3">{a.name}</td>
                        <td className="py-1 pe-3 opacity-70">{a.account_type}</td>
                        <td className={`py-1 text-end tabular-nums font-medium ${a.balance >= 0 ? '' : 'opacity-80'}`}>
                          {formatCurrency(a.balance)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {/* Show numeric fields */}
          {['assets_total', 'liabilities_total_raw', 'equity_total_raw', 'sum_all_sections',
            'cumulative_pl_balance', 'cumulative_net_profit', 'imbalance', 'cumulative_pl',
            'total_balance'].map((key) =>
            key in issue ? (
              <div key={key} className="flex items-center justify-between text-xs opacity-80">
                <span className="font-mono">{key}:</span>
                <span className="tabular-nums font-medium">{formatCurrency(issue[key])}</span>
              </div>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}

export default function Diagnostics() {
  const { filters } = useFilters();
  const { t } = useTranslation();

  const diagFilters = {
    date_to: filters.date_to,
    company_id: filters.company_id,
    posted_only: filters.posted_only,
  };

  const { data, isLoading, error, refetch } = useDiagnostic(diagFilters);
  const summary = data?.summary;

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200 rounded-xl px-6 py-5">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="bg-violet-100 rounded-xl p-2.5">
              <Stethoscope className="h-5 w-5 text-violet-600" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900">{t('diagnostics.title')}</h1>
              <p className="text-xs text-slate-500">{t('diagnostics.subtitle')}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400">{t('kpi.as_of', { date: filters.date_to })}</span>
            <button
              onClick={() => refetch()}
              disabled={isLoading}
              className="px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 transition-colors disabled:opacity-60"
            >
              {isLoading ? t('common.loading') : t('diagnostics.run')}
            </button>
          </div>
        </div>
      </div>

      <ErrorBanner error={error} />

      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      )}

      {/* KPI Summary */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <KPICard title={t('diagnostics.total_accounts')} value={summary.total_accounts?.toLocaleString()} color="indigo" />
          <KPICard title={t('diagnostics.bs_accounts')} value={summary.bs_accounts?.toLocaleString()} color="sky" />
          <KPICard title={t('diagnostics.pl_accounts')} value={summary.pl_accounts?.toLocaleString()} color="emerald" />
          <KPICard
            title={t('diagnostics.unknown_accounts')}
            value={summary.unknown_type_accounts?.toLocaleString()}
            color={summary.unknown_type_accounts > 0 ? 'amber' : 'emerald'}
          />
          <KPICard
            title={t('diagnostics.imbalance')}
            value={formatCompact(Math.abs(summary.imbalance ?? 0))}
            color={Math.abs(summary.imbalance ?? 0) < 1 ? 'emerald' : 'rose'}
          />
          <KPICard
            title={t('diagnostics.cumulative_profit')}
            value={formatCompact(summary.cumulative_net_profit)}
            color={(summary.cumulative_net_profit ?? 0) >= 0 ? 'emerald' : 'rose'}
          />
        </div>
      )}

      {/* Issues */}
      {data?.issues && data.issues.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-700 px-1">{t('diagnostics.issues')}</h2>
          {data.issues.map((issue, i) => (
            <IssueCard key={i} issue={issue} />
          ))}
        </div>
      )}

      {data && (!data.issues || data.issues.length === 0) && (
        <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-xl p-4">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 flex-shrink-0" />
          <p className="text-sm font-medium text-emerald-800">{t('diagnostics.no_issues')}</p>
        </div>
      )}
    </div>
  );
}
