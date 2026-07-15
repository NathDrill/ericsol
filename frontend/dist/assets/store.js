// store.js — session/token.
// Choix OWASP : token en mémoire (primaire) + sessionStorage (survit au reload de l'onglet,
// s'efface à la fermeture, NON partagé entre onglets). Le back exige un header Bearer
// (pas de cookie httpOnly possible sans refonte back) → on limite la surface : sessionStorage
// plutôt que localStorage (pas de persistance longue), et purge dure au 401/logout.

const KEY = 'infoclip.session';
let _mem = null;

export function getSession() {
  if (_mem) return _mem;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) _mem = JSON.parse(raw);
  } catch { _mem = null; }
  return _mem;
}

export function setSession(token, user) {
  _mem = { token, user };
  try { sessionStorage.setItem(KEY, JSON.stringify(_mem)); } catch {}
}

export function getToken() { const s = getSession(); return s && s.token; }
export function getUser() { const s = getSession(); return s && s.user; }

export function clearSession() {
  _mem = null;
  try { sessionStorage.removeItem(KEY); } catch {}
}
