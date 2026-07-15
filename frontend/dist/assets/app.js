// app.js — bootstrap, layout applicatif (sidebar + topbar), garde d'authentification, table de routage.
import { el, mount, clear, icon } from './dom.js?v=2';
import { getSession, getUser, clearSession } from './store.js?v=2';
import { route, setNotFound, setOnNavigate, startRouter, navigate, currentPath } from './router.js?v=2';
import { renderLogin } from './pages/login.js?v=2';
import { renderDashboard } from './pages/dashboard.js?v=2';
import { renderContracts } from './pages/contracts.js?v=2';
import { renderContractDetail } from './pages/contract-detail.js?v=2';
import { renderResiliations } from './pages/resiliations.js?v=2';
import { renderVendors } from './pages/vendors.js?v=2';
import { renderAsk } from './pages/ask.js?v=2';

const root = document.getElementById('app');

// Navigation visible. Paramètres & Intégrations : volontairement ABSENTS du menu
// (code conservé côté API mais non exposé, cf. demande produit).
const NAV = [
  { path: '/', label: 'Tableau de bord', icon: 'dashboard' },
  { path: '/ask', label: 'Poser une question', icon: 'chat' },
  { path: '/contracts', label: 'Contrats', icon: 'contract' },
  { path: '/resiliations', label: 'Résiliations', icon: 'clock' },
  { path: '/vendors', label: 'Fournisseurs', icon: 'vendors' },
];

let contentHost = null;

function layout() {
  const user = getUser() || {};
  const sidebar = el('aside', { class: 'sidebar' }, [
    el('div', { class: 'brand' }, [
      el('div', { class: 'brand-mark', text: 'IC' }),
      el('div', { class: 'brand-text' }, [
        el('strong', { text: 'Infoclip' }),
        el('span', { text: 'Gestion de contrats' }),
      ]),
    ]),
    el('nav', { class: 'nav' }, NAV.map((item) =>
      el('a', {
        class: 'nav-item', href: '#' + item.path, dataset: { path: item.path },
      }, [icon(item.icon), el('span', { text: item.label })])
    )),
    el('div', { class: 'sidebar-foot' }, [
      el('div', { class: 'user-chip' }, [
        el('div', { class: 'avatar', text: (user.full_name || user.email || '?').slice(0, 1).toUpperCase() }),
        el('div', { class: 'user-meta' }, [
          el('strong', { text: user.full_name || 'Utilisateur' }),
          el('span', { text: user.email || '' }),
        ]),
      ]),
      el('button', { class: 'btn btn-ghost btn-logout', onClick: doLogout }, [icon('logout', 18), el('span', { text: 'Déconnexion' })]),
    ]),
  ]);

  contentHost = el('main', { class: 'content' });
  return el('div', { class: 'shell' }, [sidebar, contentHost]);
}

function highlightNav(path) {
  document.querySelectorAll('.nav-item').forEach((a) => {
    const p = a.dataset.path;
    const active = p === '/' ? path === '/' : path.startsWith(p);
    a.classList.toggle('active', active);
  });
}

function doLogout() { clearSession(); navigate('/login'); }

// Rend une page authentifiée dans le shell (le construit une fois, puis réutilise contentHost).
function shellPage(renderFn, params, query) {
  if (!getSession()) { navigate('/login'); return; }
  if (!document.querySelector('.shell')) mount(root, layout());
  highlightNav(currentPath());
  renderFn(contentHost, params, query);
}

function mountLogin() {
  clear(root);
  contentHost = null;
  renderLogin(root, () => navigate('/'));
}

// Routes
route('/login', mountLogin);
route('/', (p, q) => shellPage(renderDashboard, p, q));
route('/ask', (p, q) => shellPage(renderAsk, p, q));
route('/contracts', (p, q) => shellPage(renderContracts, p, q));
route('/contracts/:id', (p, q) => shellPage(renderContractDetail, p, q));
route('/resiliations', (p, q) => shellPage(renderResiliations, p, q));
route('/vendors', (p, q) => shellPage(renderVendors, p, q));
setNotFound(() => shellPage(renderDashboard, {}, {}));
setOnNavigate((path) => { if (path !== '/login') highlightNav(path); });

startRouter();
