import axios from 'axios';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 120000, // 2 min for first uncached requests
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message;
    console.error('API Error:', msg);
    return Promise.reject(err);
  }
);

export default client;
