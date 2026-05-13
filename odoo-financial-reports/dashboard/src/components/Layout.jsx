import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useLanguage } from '../context/LanguageContext';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { isRTL } = useLanguage();

  // Ctrl+R → refresh
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        qc.invalidateQueries();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [qc]);

  return (
    <div className={`flex h-screen overflow-hidden bg-slate-50 ${isRTL ? 'flex-row-reverse' : ''}`}>
      <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
        <footer className={`px-6 py-2 border-t border-slate-200 bg-white ${isRTL ? 'text-right' : ''}`}>
          <p className="text-xs text-slate-400">
            {t('safety.badge')} · Odoo 17 Enterprise · Palme · {new Date().getFullYear()}
          </p>
        </footer>
      </div>
    </div>
  );
}
