// contracts.js — liste des contrats : recherche, filtre par statut, tri, upload+analyse PDF.
import { el, mount, money, dateFR, icon } from '../dom.js';
import { api } from '../api.js';
import { spinner, errorState, pageHeader, statusBadge, toast } from '../ui.js';
import { navigate } from '../router.js';
import { openAnalyzePanel } from './analyze.js';

const STATUS_FILTERS = [
  { k: 'all', label: 'Tous' }, { k: 'actif', label: 'Actifs' },
  { k: 'a_resilier', label: 'À résilier' }, { k: 'deadline_depassee', label: 'Échéance dépassée' },
  { k: 'resilie', label: 'Résiliés' }, { k: 'expire', label: 'Expirés' },
];

let state = { q: '', status: 'all', items: [] };

export async function renderContracts(host) {
  mount(host, spinner('Chargement des contrats…'));
  let data;
  try { data = await api.contracts(); }
  catch (err) { mount(host, errorState(err.message, () => renderContracts(host))); return; }
  state.items = data.items || [];

  const listHost = el('div', { class: 'table-wrap' });

  const search = el('input', {
    class: 'input input-search', type: 'search', attrs: { placeholder: 'Rechercher un contrat, un fournisseur…' },
    value: state.q, onInput: (e) => { state.q = e.target.value; drawList(listHost); },
  });

  const filters = el('div', { class: 'chips' }, STATUS_FILTERS.map((f) =>
    el('button', {
      class: 'chip chip-btn' + (state.status === f.k ? ' chip-active' : ''),
      text: f.label, dataset: { k: f.k },
      onClick: (e) => {
        state.status = f.k;
        filters.querySelectorAll('.chip-btn').forEach((c) => c.classList.toggle('chip-active', c.dataset.k === f.k));
        drawList(listHost);
      },
    })
  ));

  const analyzeBtn = el('button', { class: 'btn btn-primary', onClick: () => openAnalyzePanel(() => renderContracts(host)) },
    [icon('upload', 18), el('span', { text: 'Analyser un PDF' })]);

  mount(host, el('div', { class: 'page' }, [
    pageHeader('Contrats', state.items.length + ' contrat' + (state.items.length > 1 ? 's' : '') + ' suivis', [analyzeBtn]),
    el('div', { class: 'toolbar' }, [search, filters]),
    listHost,
  ]));
  drawList(listHost);
}

function drawList(listHost) {
  const q = state.q.trim().toLowerCase();
  let rows = state.items.filter((c) => state.status === 'all' || c.status === state.status);
  if (q) rows = rows.filter((c) =>
    (c.title || '').toLowerCase().includes(q) ||
    (c.legal_entity || '').toLowerCase().includes(q) ||
    (c.source_filename || '').toLowerCase().includes(q)
  );
  rows = rows.slice().sort((a, b) => (b.amount_mrr || 0) - (a.amount_mrr || 0));

  if (!rows.length) {
    mount(listHost, el('div', { class: 'empty' }, [el('div', { class: 'empty-title', text: 'Aucun contrat ne correspond' })]));
    return;
  }
  const table = el('table', { class: 'table' }, [
    el('thead', {}, el('tr', {}, [
      el('th', { text: 'Contrat' }), el('th', { text: 'MRR' }), el('th', { text: 'Récurrence' }),
      el('th', { text: 'Échéance résiliation' }), el('th', { text: 'Reconduction' }), el('th', { text: 'Statut' }),
    ])),
    el('tbody', {}, rows.map((c) =>
      el('tr', { class: 'row-click', onClick: () => navigate('/contracts/' + c.id) }, [
        el('td', {}, [
          el('strong', { text: c.title || 'Contrat #' + c.id }),
          c.legal_entity ? el('div', { class: 'muted small', text: c.legal_entity }) : null,
        ]),
        el('td', { class: 'num', text: money(c.amount_mrr) }),
        el('td', { text: recurrenceLabel(c.recurrence) }),
        el('td', { text: c.cancel_deadline_label || dateFR(c.cancel_deadline) }),
        el('td', {}, c.has_auto_renewal ? el('span', { class: 'chip chip-muted', text: 'Tacite' }) : el('span', { class: 'muted', text: 'Non' })),
        el('td', {}, statusBadge(c.status)),
      ])
    )),
  ]);
  mount(listHost, table);
}

function recurrenceLabel(r) {
  return ({ monthly: 'Mensuel', quarterly: 'Trimestriel', semiannual: 'Semestriel', annual: 'Annuel', biannual: 'Bisannuel' })[r] || r || '—';
}
