import client from './client';

export const fetchHealth = () => client.get('/health').then((r) => r.data);
export const fetchCompanies = () => client.get('/companies').then((r) => r.data);
export const fetchDateRange = () => client.get('/date-range').then((r) => r.data);
export const fetchSafetyStatus = () => client.get('/safety-status').then((r) => r.data);
export const fetchCacheStats = () => client.get('/cache/stats').then((r) => r.data);
export const clearCache = () => client.post('/cache/clear').then((r) => r.data);
