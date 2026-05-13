import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export async function sendChat(payload) {
  const { data } = await axios.post(`${BASE}/api/v1/chat`, payload);
  return data;
}

export async function getChatStatus() {
  const { data } = await axios.get(`${BASE}/api/v1/chat/status`);
  return data;
}
