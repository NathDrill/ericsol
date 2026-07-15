// vendors.js — fournisseurs classés par dépense (MRR / ARR).
import { el, mount, money, moneyPrecise } from '../dom.js';
import { api } from '../api.js';
import { spinner, errorState, pageHeader } from '../ui.js';

let metric = 'mrr';

export async function renderVendors(host) {
  mount(host, spinner('Chargement des fournisseurs…'));
  let vendors;
  try { vendors = await api.topVendors(metric, 50); }
  catch (err) { mount(host, errorState(err.message, () => renderVendors(host))); return; }

  const toggle = el('div', { class: 'chips' }, [
    metricBtn('mrr', 'Mensuel (MRR)'),
    metricBtn('arr', 'Annuel (ARR)'),
  ]);
  function metricBtn(k, label) {
    return el('button', { class: 'chip chip-btn' + (metric === k ? ' chip-active' : ''), text: label, onClick: () => { metric = k; renderVendors(host); } });
  }

  const max = Math.max(1, ...vendors.map((v) => Number(v[metric] || 0)));
  const content = vendors.length
    ? el('div', { class: 'vendor-bars' }, vendors.map((v) => {
        const val = Number(v[metric] || 0);
        const bar = el('div', { class: 'bar-fill' });
        bar.style.width = Math.max(2, (val / max) * 100) + '%';
        return el('div', { class: 'vendor-bar-row' }, [
          el('div', { class: 'vendor-bar-head' }, [
            el('strong', { text: v.name || '—' }),
            el('span', { class: 'muted small', text: (v.count || 0) + ' contrat' + (v.count > 1 ? 's' : '') }),
          ]),
          el('div', { class: 'bar-track' }, [bar]),
          el('div', { class: 'vendor-bar-val', text: moneyPrecise(val) + (metric === 'mrr' ? '/mois' : '/an') }),
        ]);
      }))
    : el('div', { class: 'empty' }, [el('div', { class: 'empty-title', text: 'Aucun fournisseur' })]);

  mount(host, el('div', { class: 'page' }, [
    pageHeader('Fournisseurs', 'Répartition de la dépense par fournisseur', [toggle]),
    content,
  ]));
}
