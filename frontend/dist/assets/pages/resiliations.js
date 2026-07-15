// resiliations.js — fenêtres de résiliation à venir (calculées côté back : préavis + reconduction).
import { el, mount, dateFR, daysUntil } from '../dom.js';
import { api } from '../api.js';
import { spinner, errorState, pageHeader, statusBadge, toast } from '../ui.js';
import { navigate } from '../router.js';

let horizon = 24;

export async function renderResiliations(host) {
  mount(host, spinner('Calcul des fenêtres de résiliation…'));
  let data;
  try { data = await api.cancellationWindows({ filter_current: true, horizon_months: horizon }); }
  catch (err) { mount(host, errorState(err.message, () => renderResiliations(host))); return; }

  const rows = (data.items || []).slice().sort((a, b) => (a.deadline || '').localeCompare(b.deadline || ''));

  const horizonSel = el('select', { class: 'input input-inline', onChange: (e) => { horizon = Number(e.target.value); renderResiliations(host); } },
    [12, 24, 36].map((m) => el('option', { value: String(m), text: m + ' mois', selected: m === horizon })));

  const content = rows.length
    ? el('div', { class: 'table-wrap' }, [
        el('table', { class: 'table' }, [
          el('thead', {}, el('tr', {}, [
            el('th', { text: 'Contrat' }), el('th', { text: 'Fenêtre à partir du' }),
            el('th', { text: 'Date limite de résiliation' }), el('th', { text: 'Échéance' }),
            el('th', { text: 'Statut' }), el('th', { text: '' }),
          ])),
          el('tbody', {}, rows.map((r) => {
            const d = daysUntil(r.deadline);
            const urgent = d != null && d <= 30 && d >= 0;
            return el('tr', { class: 'row-click' + (urgent ? ' row-urgent' : ''), onClick: () => navigate('/contracts/' + r.id) }, [
              el('td', {}, [el('strong', { text: r.title || 'Contrat #' + r.id }), r.legal_entity ? el('div', { class: 'muted small', text: r.legal_entity }) : null]),
              el('td', { text: dateFR(r.window_earliest || r.window_start) }),
              el('td', {}, [el('strong', { text: dateFR(r.deadline) })]),
              el('td', {}, d != null ? el('span', { class: 'chip ' + (urgent ? 'chip-warn' : 'chip-muted'), text: d >= 0 ? 'J-' + d : 'dépassé' }) : el('span', { text: '—' })),
              el('td', {}, statusBadge(r.status)),
              el('td', {}, r.status !== 'resilie'
                ? el('button', { class: 'btn btn-sm btn-danger', text: 'Résilier', onClick: async (e) => {
                    e.stopPropagation(); e.target.disabled = true;
                    try { await api.markResilie(r.id); toast('Contrat marqué comme résilié.', 'success'); renderResiliations(host); }
                    catch (err) { toast(err.message, 'error'); e.target.disabled = false; }
                  } })
                : el('span', { class: 'muted small', text: 'Résilié' })),
            ]);
          })),
        ]),
      ])
    : el('div', { class: 'empty' }, [
        el('div', { class: 'empty-title', text: 'Aucune fenêtre de résiliation' }),
        el('div', { class: 'empty-sub', text: 'Aucun contrat n\'a de fenêtre de résiliation sur l\'horizon sélectionné.' }),
      ]);

  mount(host, el('div', { class: 'page' }, [
    pageHeader('Résiliations', 'Fenêtres d\'opportunité pour résilier avant reconduction', [
      el('label', { class: 'inline-field' }, [el('span', { class: 'muted small', text: 'Horizon' }), horizonSel]),
    ]),
    content,
  ]));
}
