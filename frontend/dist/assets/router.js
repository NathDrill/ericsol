// router.js — routeur hash minimal (pas de config serveur requise).
const routes = [];
let notFound = null;
let onNavigate = null;

export function route(pattern, handler) {
  // pattern ex: '/contracts/:id' → regex + noms de params
  const names = [];
  const rx = new RegExp('^' + pattern.replace(/:[^/]+/g, (m) => { names.push(m.slice(1)); return '([^/]+)'; }) + '$');
  routes.push({ rx, names, handler });
}
export function setNotFound(h) { notFound = h; }
export function setOnNavigate(h) { onNavigate = h; }

export function currentPath() {
  const h = location.hash.replace(/^#/, '');
  return h.split('?')[0] || '/';
}
export function navigate(path) { location.hash = '#' + path; }

export function parseQuery() {
  const h = location.hash.replace(/^#/, '');
  const qs = h.includes('?') ? h.split('?')[1] : '';
  return Object.fromEntries(new URLSearchParams(qs));
}

async function resolve() {
  const path = currentPath();
  for (const r of routes) {
    const m = path.match(r.rx);
    if (m) {
      const params = {};
      r.names.forEach((n, i) => { params[n] = decodeURIComponent(m[i + 1]); });
      if (onNavigate) onNavigate(path);
      return r.handler(params, parseQuery());
    }
  }
  if (notFound) notFound();
}

export function startRouter() {
  window.addEventListener('hashchange', resolve);
  resolve();
}
