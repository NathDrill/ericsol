// dom.js — helpers de rendu 100% XSS-safe.
// Règle OWASP : aucune donnée dynamique n'est jamais injectée en HTML.
// On ne construit le DOM que via createElement + textContent. Pas d'innerHTML avec des données.

/**
 * el(tag, props?, children?) — crée un élément sûr.
 * props: { class, text, html?(interdit pour data), onClick, attrs:{}, style:{}, ...directProps }
 * children: string | Node | Array<string|Node|null|false>
 */
export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;           // toujours textContent → pas de XSS
    else if (k === 'html') throw new Error('html interdit : utiliser text');
    else if (k === 'onClick') node.addEventListener('click', v);
    else if (k === 'onInput') node.addEventListener('input', v);
    else if (k === 'onChange') node.addEventListener('change', v);
    else if (k === 'onSubmit') node.addEventListener('submit', v);
    else if (k === 'attrs') for (const [ak, av] of Object.entries(v)) { if (av != null) node.setAttribute(ak, av); }
    else if (k === 'style') for (const [sk, sv] of Object.entries(v)) node.style[sk] = sv;  // CSSOM, pas d'attribut inline
    else if (k === 'dataset') for (const [dk, dv] of Object.entries(v)) node.dataset[dk] = dv;
    else node[k] = v;
  }
  append(node, children);
  return node;
}

export function append(node, children) {
  const list = Array.isArray(children) ? children : [children];
  for (const c of list) {
    if (c == null || c === false || c === '') continue;
    node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

export function mount(node, children) { clear(node); append(node, children); return node; }

// Icônes SVG inline (chaînes de confiance, définies par nous — pas de données utilisateur).
// Rendu via un <svg> construit par le parseur, sûr car statique et contrôlé.
const ICONS = {
  dashboard: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  contract: 'M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6H6zm7 1.5L18.5 9H13V3.5zM8 12h8v2H8v-2zm0 4h8v2H8v-2z',
  clock: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 10.4 4 2.3-1 1.7-5-2.9V7h2v5.4z',
  vendors: 'M12 2 2 7v2h20V7L12 2zM4 11v7H2v2h20v-2h-2v-7h-2v7h-3v-7h-2v7h-2v-7H9v7H6v-7H4z',
  logout: 'M16 13v-2H7V8l-5 4 5 4v-3h9zM20 3h-8v2h8v14h-8v2h8a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2z',
  upload: 'M12 2 6 8h4v6h4V8h4l-6-6zM4 18h16v2H4v-2z',
  chat: 'M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 9h12v2H6V9zm8 5H6v-2h8v2zm4-6H6V6h12v2z',
  send: 'M2.01 21 23 12 2.01 3 2 10l15 2-15 2z',
};
export function icon(name, size = 20) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size); svg.setAttribute('height', size);
  svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('fill', 'currentColor');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', ICONS[name] || '');
  svg.appendChild(path);
  return svg;
}

// Formatage
export function money(v) {
  const n = Number(v || 0);
  return n.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
}
export function moneyPrecise(v) {
  return Number(v || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
}
export function dateFR(iso) {
  if (!iso) return '—';
  const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''));
  if (isNaN(d)) return '—';
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
}
export function daysUntil(iso) {
  if (!iso) return null;
  const d = new Date(iso + 'T00:00:00');
  return Math.round((d - new Date(new Date().toDateString())) / 86400000);
}
