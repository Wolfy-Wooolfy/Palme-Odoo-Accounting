import { FileSearch } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function EmptyState({ title, message, icon: Icon = FileSearch }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="bg-slate-100 rounded-full p-4 mb-4">
        <Icon className="h-8 w-8 text-slate-400" />
      </div>
      <h3 className="text-slate-700 font-semibold text-lg mb-1">{title ?? t('common.no_data')}</h3>
      {message && <p className="text-slate-500 text-sm max-w-xs">{message}</p>}
    </div>
  );
}
