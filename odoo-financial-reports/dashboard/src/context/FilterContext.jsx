import { createContext, useContext, useState } from 'react';
import { fmt, DATE_PRESETS } from '../utils/dateHelpers';

const FilterContext = createContext(null);

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// Normalise a raw filter object — guards against stale localStorage data that
// would send an invalid payload and trigger a backend 422.
function sanitizeFilters(obj) {
  if (!obj || typeof obj !== 'object') return null;
  const { date_from, date_to, company_id, posted_only } = obj;
  if (!DATE_RE.test(date_from) || !DATE_RE.test(date_to)) return null;
  const cid =
    company_id == null || company_id === '' || Number.isNaN(+company_id)
      ? null
      : Number.isInteger(+company_id) && +company_id > 0
        ? +company_id
        : null;
  return {
    date_from,
    date_to,
    company_id: cid,
    posted_only: typeof posted_only === 'boolean' ? posted_only : true,
  };
}

const getDefault = () => {
  try {
    const saved = localStorage.getItem('odoo-report-filters');
    if (saved) {
      const sanitized = sanitizeFilters(JSON.parse(saved));
      if (sanitized) return sanitized;
    }
  } catch {}
  // Default: Last Year — always has data
  return DATE_PRESETS.find((p) => p.label === 'Last Year').getValue();
};

export function FilterProvider({ children }) {
  const [filters, setFiltersState] = useState(() => ({
    ...getDefault(),
    company_id: null,
    posted_only: true,
  }));

  const setFilters = (partial) => {
    setFiltersState((prev) => {
      const merged = { ...prev, ...partial };
      const next = sanitizeFilters(merged) ?? merged;
      try {
        localStorage.setItem('odoo-report-filters', JSON.stringify(next));
      } catch {}
      return next;
    });
  };

  return (
    <FilterContext.Provider value={{ filters, setFilters }}>
      {children}
    </FilterContext.Provider>
  );
}

export const useFilters = () => useContext(FilterContext);
