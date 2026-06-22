import { useLocation } from 'react-router-dom';
import { RefreshCw, Globe } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useLanguage } from '../context/LanguageContext';
import SafetyBadge from './SafetyBadge';

const PAGE_TITLE_KEYS = {
  '/': 'nav.overview',
  '/trial-balance': 'nav.trial_balance',
  '/profit-loss': 'nav.profit_loss',
  '/balance-sheet': 'nav.balance_sheet',
  '/pos-sessions': 'nav.pos_sessions',
  '/settings': 'nav.settings',
};

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
      <h1 className="text-lg font-semibold text-slate-900 truncate">{t(titleKey)}</h1>
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
