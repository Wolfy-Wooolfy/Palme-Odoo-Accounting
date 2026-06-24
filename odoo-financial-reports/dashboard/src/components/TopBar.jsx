import { useLocation } from 'react-router-dom';
import { RefreshCw, Globe, Building2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useLanguage } from '../context/LanguageContext';
import { useFilters } from '../context/FilterContext';
import { useCompanies } from '../hooks/useMeta';
import SafetyBadge from './SafetyBadge';

const PAGE_TITLE_KEYS = {
  '/': 'nav.overview',
  '/trial-balance': 'nav.trial_balance',
  '/profit-loss': 'nav.profit_loss',
  '/balance-sheet': 'nav.balance_sheet',
  '/pos-sessions': 'nav.pos_sessions',
  '/visa-reconciliation': 'nav.visa_reconciliation',
  '/bank-movements': 'nav.bank_movements',
  '/settings': 'nav.settings',
};

// Always-visible indicator of the company the global filter is currently scoped to.
// Reads the SAME FilterContext state the FilterPanel writes, so switching company in
// the panel updates this badge immediately. null company_id → "All companies".
function CurrentCompanyBadge() {
  const { filters } = useFilters();
  const { data: companies = [] } = useCompanies();
  const { t } = useTranslation();
  const company = companies.find((c) => c.id === filters.company_id);
  const label =
    filters.company_id == null
      ? t('common.all_companies')
      : company?.name ?? `#${filters.company_id}`;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-primary-50 border border-primary-100 text-xs flex-shrink-0"
      title={t('common.current_company')}
      dir="auto"
    >
      <Building2 className="h-3.5 w-3.5 text-primary-400 flex-shrink-0" />
      <span className="text-primary-400 font-normal hidden sm:inline">{t('common.current_company')}:</span>
      <span className="font-semibold text-primary-700">{label}</span>
    </span>
  );
}

function LanguageSwitcher() {
  const { language, changeLanguage } = useLanguage();
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-1.5">
      <Globe className="h-4 w-4 text-slate-400" />
      <select
        value={language}
        onChange={(e) => changeLanguage(e.target.value)}
        className="text-sm bg-transparent border border-slate-200 rounded-md px-2 py-1 cursor-pointer hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary-300"
      >
        <option value="en">{t('common.english')}</option>
        <option value="ar">{t('common.arabic')}</option>
      </select>
    </div>
  );
}

export default function TopBar() {
  const location = useLocation();
  const qc = useQueryClient();
  const { t } = useTranslation();
  const titleKey = PAGE_TITLE_KEYS[location.pathname] || 'nav.overview';

  return (
    <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3 min-w-0">
        <h1 className="text-lg font-semibold text-slate-900 truncate">{t(titleKey)}</h1>
        <CurrentCompanyBadge />
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        <LanguageSwitcher />
        <button
          onClick={() => qc.invalidateQueries()}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50 transition-colors"
          title={`${t('common.refresh')} (Ctrl+R)`}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          {t('common.refresh')}
        </button>
        <SafetyBadge />
      </div>
    </header>
  );
}
