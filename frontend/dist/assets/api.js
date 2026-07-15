// api.js — client HTTP unique. Même origine (connect-src 'self'), Bearer token, gestion 401.
import { getToken, clearSession } from './store.js?v=2';

const BASE = '/api';

class ApiError extends Error {
  constructor(status, message, payload) { super(message); this.status = status; this.payload = payload; }
}
export { ApiError };

async function request(method, path, { body, form, query, raw } = {}) {
  const url = new URL(BASE + path, location.origin);
  if (query) for (const [k, v] of Object.entries(query)) if (v != null) url.searchParams.set(k, v);

  const headers = {};
  const token = getToken();
  if (token) headers['Authorization'] = 'Bearer ' + token;

  let payload;
  if (form) { payload = form; }                                  // FormData ou URLSearchParams : pas de Content-Type manuel
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }

  let res;
  try {
    res = await fetch(url, { method, headers, body: payload, credentials: 'same-origin' });
  } catch (e) {
    throw new ApiError(0, 'Réseau indisponible. Vérifiez votre connexion.');
  }

  if (res.status === 401) {
    clearSession();
    if (!location.hash.startsWith('#/login')) location.hash = '#/login';
    throw new ApiError(401, 'Session expirée, reconnectez-vous.');
  }
  if (raw) {
    if (!res.ok) throw new ApiError(res.status, 'Téléchargement impossible.');
    return res;
  }
  let data = null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) { try { data = await res.json(); } catch {} }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `Erreur ${res.status}`;
    throw new ApiError(res.status, typeof msg === 'string' ? msg : 'Erreur serveur', data);
  }
  return data;
}

export const api = {
  // Auth
  login: (username, password) => {
    const form = new URLSearchParams(); form.set('username', username); form.set('password', password);
    return request('POST', '/auth/login', { form });
  },
  me: () => request('GET', '/auth/me'),

  // Contrats
  contracts: () => request('GET', '/contracts'),
  contract: (id) => request('GET', `/contracts/${encodeURIComponent(id)}`),
  stats: () => request('GET', '/contracts/stats'),
  cancellationWindows: (q) => request('GET', '/contracts/cancellation-windows', { query: q }),
  markResilie: (id) => request('PUT', `/contracts/${encodeURIComponent(id)}/marquer-resilie`),
  updateContract: (id, body) => request('PUT', `/contracts/${encodeURIComponent(id)}`, { body }),
  analyzePdf: (file) => { const fd = new FormData(); fd.append('file', file); return request('POST', '/contracts/analyze-pdf', { form: fd }); },
  downloadUrl: (id) => `${BASE}/contracts/${encodeURIComponent(id)}/download`,
  downloadRaw: (id) => request('GET', `/contracts/${encodeURIComponent(id)}/download`, { raw: true, query: { inline: 'true' } }),
  qaAsk: (id, question) => { const form = new URLSearchParams(); form.set('question', question); return request('POST', `/contracts/${encodeURIComponent(id)}/qa`, { form }); },
  qaGlobal: (question, history) => request('POST', '/ai/qa', { body: { question, history } }),

  // Fournisseurs
  topVendors: (metric = 'mrr', limit = 8) => request('GET', '/vendors/top', { query: { metric, limit } }),

  // Réglages (menu masqué mais endpoint conservé)
  notifications: () => request('GET', '/settings/notifications'),
  saveNotifications: (body) => request('PUT', '/settings/notifications', { body }),
};
