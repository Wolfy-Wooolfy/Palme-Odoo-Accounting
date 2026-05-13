import clsx from 'clsx';
import { SkeletonCard } from './LoadingSpinner';

export default function KPICard({ title, value, subtitle, icon: Icon, color = 'indigo', loading = false }) {
  if (loading) return <SkeletonCard />;

  const colors = {
    indigo: 'bg-primary-50 text-primary-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    rose: 'bg-rose-50 text-rose-600',
    amber: 'bg-amber-50 text-amber-600',
    sky: 'bg-sky-50 text-sky-600',
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <p className="text-sm font-medium text-slate-500">{title}</p>
        {Icon && (
          <div className={clsx('rounded-lg p-2', colors[color])}>
            <Icon className="h-4 w-4" />
          </div>
        )}
      </div>
      <p className="text-2xl font-bold text-slate-900 tabular-nums leading-tight">{value ?? '—'}</p>
      {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
    </div>
  );
}
