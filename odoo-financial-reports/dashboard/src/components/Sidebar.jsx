import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Scale, TrendingUp, BookOpen, Settings,
  ChevronLeft, ChevronRight, Users, Truck, Landmark, BookMarked,
  ShoppingCart, Package, Stethoscope, Sparkles, Store, CreditCard,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLanguage } from '../context/LanguageContext';
import clsx from 'clsx';

const NAV_GROUPS = [
  {
    key: 'group_overview',
    items: [
      { to: '/', icon: LayoutDashboard, key: 'nav.overview', exact: true },
    ],
  },
  {
    key: 'group_financial',
    items: [
      { to: '/trial-balance', icon: Scale, key: 'nav.trial_balance' },
      { to: '/profit-loss', icon: TrendingUp, key: 'nav.profit_loss' },
      { to: '/balance-sheet', icon: BookOpen, key: 'nav.balance_sheet' },
      { to: '/general-ledger', icon: BookMarked, key: 'nav.general_ledger' },
    ],
  },
  {
    key: 'group_aging',
    items: [
      { to: '/customer-aging', icon: Users, key: 'nav.customer_aging' },
      { to: '/vendor-aging', icon: Truck, key: 'nav.vendor_aging' },
    ],
  },
  {
    key: 'group_cash',
    items: [
      { to: '/cash-bank', icon: Landmark, key: 'nav.cash_bank' },
    ],
  },
  {
    key: 'group_activity',
    items: [
      { to: '/sales', icon: ShoppingCart, key: 'nav.sales' },
      { to: '/purchases', icon: Package, key: 'nav.purchases' },
    ],
  },
  {
    // Fully-qualified i18n key so the group label resolves under the `nav` namespace.
    key: 'nav.group_operations',
    items: [
      { to: '/pos-sessions', icon: Store, key: 'nav.pos_sessions' },
      { to: '/visa-reconciliation', icon: CreditCard, key: 'nav.visa_reconciliation' },
    ],
  },
  {
    key: 'group_system',
    items: [
      { to: '/diagnostics', icon: Stethoscope, key: 'nav.diagnostics' },
      { to: '/settings', icon: Settings, key: 'nav.settings' },
    ],
  },
  {
    key: 'group_ai',
    items: [
      { to: '/chat', icon: Sparkles, key: 'nav.ai_chat' },
    ],
  },
];

export default function Sidebar({ collapsed, setCollapsed }) {
  const { t } = useTranslation();
  const { isRTL } = useLanguage();

  const CollapseIcon = isRTL
    ? collapsed ? ChevronLeft : ChevronRight
    : collapsed ? ChevronRight : ChevronLeft;

  return (
    <aside className={clsx(
      'flex flex-col bg-slate-900 text-slate-300 transition-all duration-200 flex-shrink-0 overflow-y-auto',
      collapsed ? 'w-16' : 'w-56'
    )}>
      {/* Logo */}
      <div className={clsx(
        'flex items-center gap-3 px-4 py-5 border-b border-slate-700/50 flex-shrink-0',
        collapsed && 'justify-center px-3'
      )}>
        <div className="flex-shrink-0 bg-primary-600 rounded-lg p-1.5">
          <svg viewBox="0 0 24 24" className="h-5 w-5 fill-white">
            <rect x="2" y="14" width="4" height="8" rx="1"/>
            <rect x="10" y="9" width="4" height="13" rx="1"/>
            <rect x="18" y="4" width="4" height="18" rx="1"/>
          </svg>
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="text-white font-semibold text-sm leading-tight truncate">{t('app.name')}</p>
            <p className="text-slate-500 text-xs truncate">{t('app.subtitle')}</p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 space-y-3">
        {NAV_GROUPS.map((group) => (
          <div key={group.key}>
            {!collapsed && (
              <p className="text-slate-500 text-xs font-semibold uppercase tracking-wider px-3 mb-1">
                {t(group.key)}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map(({ to, icon: Icon, key, exact }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={exact}
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                      isActive ? 'bg-primary-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100',
                      collapsed && 'justify-center px-2'
                    )
                  }
                  title={collapsed ? t(key) : undefined}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  {!collapsed && <span className="truncate">{t(key)}</span>}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex items-center justify-center p-4 border-t border-slate-700/50 text-slate-500 hover:text-slate-300 transition-colors flex-shrink-0"
      >
        <CollapseIcon className="h-4 w-4" />
      </button>
    </aside>
  );
}
