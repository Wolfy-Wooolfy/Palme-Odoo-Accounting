import i18n from '../i18n';

const locale = () => (i18n.language?.startsWith('ar') ? 'ar-EG-u-nu-latn' : 'en-US');

export const formatCurrency = (amount, currency = 'EGP') => {
  if (amount === null || amount === undefined) return '—';
  return (
    new Intl.NumberFormat(locale(), {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount) +
    ' ' +
    currency
  );
};

export const formatCompact = (amount, currency = 'EGP') => {
  if (amount === null || amount === undefined) return '—';
  const isAr = i18n.language?.startsWith('ar');
  const abs = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';
  if (abs >= 1_000_000_000) {
    const v = (abs / 1_000_000_000).toFixed(2);
    return isAr ? `${sign}${v} مليار ${currency}` : `${sign}${v}B ${currency}`;
  }
  if (abs >= 1_000_000) {
    const v = (abs / 1_000_000).toFixed(2);
    return isAr ? `${sign}${v} مليون ${currency}` : `${sign}${v}M ${currency}`;
  }
  if (abs >= 1_000) {
    const v = (abs / 1_000).toFixed(2);
    return isAr ? `${sign}${v} ألف ${currency}` : `${sign}${v}K ${currency}`;
  }
  return `${sign}${abs.toFixed(2)} ${currency}`;
};

export const formatPercent = (value) => {
  if (value === null || value === undefined || !isFinite(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
};

export const formatDate = (dateStr) => {
  if (!dateStr) return '—';
  const loc = i18n.language?.startsWith('ar') ? 'ar-EG' : 'en-GB';
  return new Date(dateStr).toLocaleDateString(loc, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

export const formatAxisCurrency = (value) => {
  // Always LTR, English numerals for chart axes
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return value.toFixed(0);
};

export const exportToCSV = (data, columns, filename) => {
  const BOM = '﻿';
  const headers = columns.map((c) => `"${c.header}"`).join(',');
  const rows = data.map((row) =>
    columns
      .map((c) => {
        const val = c.exportValue ? c.exportValue(row) : row[c.key];
        if (val === null || val === undefined) return '';
        return typeof val === 'string' ? `"${val.replace(/"/g, '""')}"` : val;
      })
      .join(',')
  );
  const csv = BOM + [headers, ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};
