import {
  format,
  startOfMonth,
  endOfMonth,
  startOfQuarter,
  endOfQuarter,
  startOfYear,
  endOfYear,
  subMonths,
  subYears,
} from 'date-fns';

export const fmt = (d) => format(d, 'yyyy-MM-dd');

export const DATE_PRESETS = [
  {
    label: 'This Month',
    getValue: () => ({ date_from: fmt(startOfMonth(new Date())), date_to: fmt(endOfMonth(new Date())) }),
  },
  {
    label: 'Last Month',
    getValue: () => {
      const lm = subMonths(new Date(), 1);
      return { date_from: fmt(startOfMonth(lm)), date_to: fmt(endOfMonth(lm)) };
    },
  },
  {
    label: 'This Quarter',
    getValue: () => ({
      date_from: fmt(startOfQuarter(new Date())),
      date_to: fmt(endOfQuarter(new Date())),
    }),
  },
  {
    label: 'YTD',
    getValue: () => ({ date_from: fmt(startOfYear(new Date())), date_to: fmt(new Date()) }),
  },
  {
    label: 'This Year',
    getValue: () => ({ date_from: fmt(startOfYear(new Date())), date_to: fmt(endOfYear(new Date())) }),
  },
  {
    label: 'Last Year',
    getValue: () => {
      const ly = subYears(new Date(), 1);
      return { date_from: fmt(startOfYear(ly)), date_to: fmt(endOfYear(ly)) };
    },
  },
];

export const matchesPreset = (dateFrom, dateTo) => {
  for (const p of DATE_PRESETS) {
    const v = p.getValue();
    if (v.date_from === dateFrom && v.date_to === dateTo) return p.label;
  }
  return 'Custom';
};
