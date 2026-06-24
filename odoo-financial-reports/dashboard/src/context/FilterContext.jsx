import { createContext, useContext, useState, useEffect, useRef } from 'react';
import { fmt, DATE_PRESETS } from '../utils/dateHelpers';
import { useCompanies } from '../hooks/useMeta';

const FilterContext = createContext(null);

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// The dashboard opens scoped to the primary operating company #بالميه#. (Odoo
// company_id 3) on EVERY screen. We seed this id synchronously so the very first
// render is already scoped to it — the companies list isn't loaded yet at init.
// Once it arrives we reconcile by NAME (the company whose name contains "بالمي"),
// so a database where #بالميه#. carries a different id still resolves correctly.
// The id is the guaranteed fallback; the name match only refines it. "All
// companies" (null) stays fully selectable — only the DEFAULT changes.
const DEFAULT_COMPANY_ID = 3;
const DEFAULT_COMPANY_NAME_TOKEN = 'بالمي';

export function resolveDefaultCompanyId(companies) {
  const match = (companies || []).find(
    (c) => typeof c?.name === 'string' && c.name.includes(DEFAULT_COMPANY_NAME_TOKEN),
  );
  return match ? match.id : DEFAULT_COMPANY_ID;
}

// Normalise a raw filter object — guards against stale localStorage data.
// Drops the object entirely (returns null) if dates are invalid ISO strings.
// Swaps date_from/date_to when reversed so PeriodFilter never rejects with 422.
function sanitizeFilters(obj) {
  if (!obj || typeof obj !== 'object') return null;
  const { company_id, posted_only } = obj;
  let { date_from, date_to } = obj;
  if (!DATE_RE.test(date_from) || !DATE_RE.test(date_to)) return null;
  if (date_from > date_to) [date_from, date_to] = [date_to, date_from];
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
  // Dates/posted_only come from localStorage (or the Last-Year preset); the company
  // ALWAYS seeds to the #بالميه#. default on a fresh load (id 3, refined by name below).
  const [filters, setFiltersState] = useState(() => ({
    ...getDefault(),
    company_id: DEFAULT_COMPANY_ID,
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

  // One-shot refinement: once the companies list loads, if the company is still the
  // seeded fallback id AND a "بالمي" company resolves to a DIFFERENT id, switch to it.
  // Guarded so it never fights a user who has already picked a company (or "all").
  const { data: companies } = useCompanies();
  const reconciledRef = useRef(false);
  useEffect(() => {
    if (reconciledRef.current || !companies || companies.length === 0) return;
    reconciledRef.current = true;
    const resolved = resolveDefaultCompanyId(companies);
    if (resolved === DEFAULT_COMPANY_ID) return;
    setFiltersState((prev) =>
      prev.company_id === DEFAULT_COMPANY_ID ? { ...prev, company_id: resolved } : prev,
    );
  }, [companies]);

  return (
    <FilterContext.Provider value={{ filters, setFilters }}>
      {children}
    </FilterContext.Provider>
  );
}

export const useFilters = () => useContext(FilterContext);
