// dashboard.js — vue d'ensemble : indicateurs, top fournisseurs, prochaines échéances de résiliation.
import { el, mount, money, moneyPrecise, dateFR, daysUntil, icon } from '../dom.js';
import { api } from '../api.js';
import { spinner, errorState, pageHeader, statusBadge } from '../ui.js';
import { navigate } from '../router.js';

const STATUS_LABEL = { actif: 'Actifs', a_resilier: 'À résilier', deadline_depassee: 'Échéance dépassée', resilie: 'Résiliés', expire: 'Expirés' };

export async function renderDashboard(host) {
  mount(host, spinner('Chargement du tableau de bord…'));
  let contracts, vendors, windows;
  try {
    [contracts, vendors, windows] = await Promise.all([
      api.contracts(),
      api.topVendors('mrr', 6).catch(() => []),
      api.cancellationWindows({ filter_current: true, horizon_months: 12 }).catch(() => ({ items: [] })),
    ]);
  } catch (err) {
    mount(host, errorState(err.message, () => renderDashboard(host)));
    return;
  }

  const ind = contracts.indicators || {};
  const counts = ind.status_counts || {};
  const upcoming = (windows.items || []).slice(0, 6);

  const kpis = el('div', { class: 'kpi-grid' }, [
    kpi('Revenu mensuel (MRR)', money(ind.mrr), 'Sur ' + (ind.count || 0) + ' contrats'),
    kpi('Revenu annualisé (ARR)', money(ind.arr), 'Projection 12 mois'),
    kpi('Contrats suivis', String(ind.count || 0), 'Portefeuille total'),
    kpi('À résilier bientôt', String((windows.items || []).length), 'Fenêtres ouvertes (12 mois)'),
  ]);

  const statusCard = el('section', { class: 'card' }, [
    el('h2', { class: 'card-title', text: 'Répartition par statut' }),
    el('div', { class: 'status-list' }, Object.keys(STATUS_LABEL).map((k) =>
      el('div', { class: 'status-row' }, [
        statusBadge(k),
        el('span', { class: 'status-count', text: String(counts[k] || 0) }),
      ])
    )),
  ]);

  const vendorCard = el('section', { class: 'card' }, [
    el('h2', { class: 'card-title', text: 'Principaux fournisseurs' }),
    (vendors && vendors.length)
      ? el('div', { class: 'vendor-list' }, vendors.map((v) =>
          el('div', { class: 'vendor-row' }, [
            el('div', { class: 'vendor-name', text: v.name || '—' }),
            el('div', { class: 'vendor-meta' }, [
              el('span', { class: 'vendor-mrr', text: moneyPrecise(v.mrr) + '/mois' }),
              el('span', { class: 'muted', text: (v.count || 0) + ' contrat' + (v.count > 1 ? 's' : '') }),
            ]),
          ])
        ))
      : el('p', { class: 'muted', text: 'Aucun fournisseur.' }),
  ]);

  const deadlineCard = el('section', { class: 'card card-wide' }, [
    el('div', { class: 'card-head' }, [
      el('h2', { class: 'card-title', text: 'Prochaines échéances de résiliation' }),
      el('a', { class: 'link', href: '#/resiliations', text: 'Tout voir →' }),
    ]),
    upcoming.length
      ? el('div', { class: 'table-wrap' }, [deadlineTable(upcoming)])
      : el('p', { class: 'muted', text: 'Aucune échéance dans les 12 prochains mois.' }),
  ]);

  mount(host, el('div', { class: 'page' }, [
    pageHeader('Tableau de bord', 'Vue consolidée de votre portefeuille de contrats'),
    kpis,
    el('div', { class: 'grid-2' }, [statusCard, vendorCard]),
    deadlineCard,
  ]));
}

function kpi(label, value, hint) {
  return el('div', { class: 'kpi' }, [
    el('div', { class: 'kpi-label', text: label }),
    el('div', { class: 'kpi-value', text: value }),
    hint ? el('div', { class: 'kpi-hint', text: hint }) : null,
  ]);
}

function deadlineTable(rows) {
  const table = el('table', { class: 'table' }, [
    el('thead', {}, el('tr', {}, [
      el('th', { text: 'Contrat' }), el('th', { text: 'Fenêtre à partir du' }),
      el('th', { text: 'Date limite' }), el('th', { text: 'Statut' }),
    ])),
    el('tbody', {}, rows.map((r) => {
      const d = daysUntil(r.deadline);
      const urgent = d != null && d <= 30;
      return el('tr', { class: 'row-click', onClick: () => navigate('/contracts/' + r.id) }, [
        el('td', {}, [el('strong', { text: r.title || 'Contrat #' + r.id }), r.legal_entity ? el('div', { class: 'muted small', text: r.legal_entity }) : null]),
        el('td', { text: dateFR(r.window_earliest || r.window_start) }),
        el('td', {}, [
          el('span', { text: dateFR(r.deadline) }),
          d != null ? el('span', { class: 'chip ' + (urgent ? 'chip-warn' : 'chip-muted'), text: d >= 0 ? 'J-' + d : 'dépassé' }) : null,
        ]),
        el('td', {}, statusBadge(r.status)),
      ]);
    })),
  ]);
  return table;
}
