// ui.js — composants réutilisables (toasts, spinner, badges, états vides).
import { el, mount } from './dom.js?v=2';

export function spinner(label = 'Chargement…') {
  return el('div', { class: 'loading' }, [el('div', { class: 'spinner' }), el('span', { text: label })]);
}

export function emptyState(title, sub) {
  return el('div', { class: 'empty' }, [
    el('div', { class: 'empty-title', text: title }),
    sub ? el('div', { class: 'empty-sub', text: sub }) : null,
  ]);
}

export function errorState(message, onRetry) {
  return el('div', { class: 'empty error-state' }, [
    el('div', { class: 'empty-title', text: 'Une erreur est survenue' }),
    el('div', { class: 'empty-sub', text: message }),
    onRetry ? el('button', { class: 'btn', text: 'Réessayer', onClick: onRetry }) : null,
  ]);
}

const STATUS_LABEL = {
  actif: 'Actif', a_resilier: 'À résilier', deadline_depassee: 'Échéance dépassée',
  resilie: 'Résilié', expire: 'Expiré',
};
export function statusBadge(status) {
  const cls = 'badge badge-' + (status || 'unknown').replace(/[^a-z_]/g, '');
  return el('span', { class: cls, text: STATUS_LABEL[status] || status || '—' });
}

// Toasts
let toastHost = null;
function host() {
  if (!toastHost) { toastHost = el('div', { class: 'toast-host' }); document.body.appendChild(toastHost); }
  return toastHost;
}
export function toast(message, kind = 'info') {
  const t = el('div', { class: 'toast toast-' + kind, text: message });
  host().appendChild(t);
  setTimeout(() => { t.classList.add('toast-out'); setTimeout(() => t.remove(), 300); }, 3500);
}

export function pageHeader(title, subtitle, actions) {
  return el('div', { class: 'page-head' }, [
    el('div', {}, [
      el('h1', { class: 'page-title', text: title }),
      subtitle ? el('p', { class: 'page-sub', text: subtitle }) : null,
    ]),
    actions ? el('div', { class: 'page-actions' }, actions) : null,
  ]);
}

export function renderInto(container, node) { mount(container, node); }

// thinkingBar — barre de progression pour un traitement IA de durée inconnue.
// Progression asymptotique (rapide au début, ralentit) vers ~92% sur estMs, puis finish() → 100%.
// Étapes affichées en rotation pour montrer que le modèle « réfléchit ».
export function thinkingBar(steps, estMs = 75000) {
  const stepList = steps && steps.length ? steps : [
    'Lecture du document…', 'Extraction des champs clés…', 'Analyse de conformité…', 'Mise en forme des résultats…',
  ];
  const fill = el('div', { class: 'pbar-fill' });
  const label = el('div', { class: 'pbar-label', text: stepList[0] });
  const pct = el('div', { class: 'pbar-pct', text: '0%' });
  const node = el('div', { class: 'pbar', attrs: { role: 'progressbar', 'aria-label': 'Analyse en cours' } }, [
    el('div', { class: 'pbar-head' }, [label, pct]),
    el('div', { class: 'pbar-track' }, [fill]),
  ]);
  const start = Date.now();
  let done = false;
  const timer = setInterval(() => {
    if (done) return;
    const t = Date.now() - start;
    const p = 92 * (1 - Math.exp(-t / (estMs * 0.5)));  // approche douce de 92%
    fill.style.width = p.toFixed(1) + '%';
    pct.textContent = Math.round(p) + '%';
    const idx = Math.min(stepList.length - 1, Math.floor((p / 92) * stepList.length));
    label.textContent = stepList[idx];
  }, 180);
  return {
    node,
    finish() { done = true; clearInterval(timer); fill.style.width = '100%'; pct.textContent = '100%'; label.textContent = 'Terminé'; node.classList.add('pbar-done'); },
    fail(msg) { done = true; clearInterval(timer); node.classList.add('pbar-fail'); label.textContent = msg || 'Échec'; },
    stop() { done = true; clearInterval(timer); },
  };
}
