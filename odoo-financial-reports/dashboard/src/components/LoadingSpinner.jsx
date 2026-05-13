import clsx from 'clsx';

export default function LoadingSpinner({ size = 'md', className = '' }) {
  const sizes = { sm: 'h-4 w-4', md: 'h-8 w-8', lg: 'h-12 w-12' };
  return (
    <div className={clsx('animate-spin rounded-full border-2 border-slate-200 border-t-primary-600', sizes[size], className)} />
  );
}

export function SkeletonRow({ cols = 6 }) {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 bg-slate-200 rounded" style={{ width: `${60 + Math.random() * 40}%` }} />
        </td>
      ))}
    </tr>
  );
}

export function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 animate-pulse">
      <div className="h-4 bg-slate-200 rounded w-24 mb-3" />
      <div className="h-8 bg-slate-200 rounded w-40 mb-2" />
      <div className="h-3 bg-slate-100 rounded w-20" />
    </div>
  );
}
