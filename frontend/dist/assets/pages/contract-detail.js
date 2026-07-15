// contract-detail.js — fiche contrat. Champs clés (temps 1) puis checklist (temps 2), Q&A, actions.
import { el, mount, clear, money, moneyPrecise, dateFR, daysUntil } from '../dom.js?v=2';
import { api } from '../api.js?v=2';
import { spinner, errorState, statusBadge, toast, thinkingBar } from '../ui.js?v=2';
import { navigate } from '../router.js?v=2';
import { renderChecklist } from './checklist.js?v=2';
import { contractEditForm } from './contract-form.js?v=2';

export async function renderContractDetail(host, params) {
  mount(host, spinner('Chargement du contrat…'));
  let c;
  try { c = await api.contract(params.id); }
  catch (err) { mount(host, errorState(err.message, () => renderContractDetail(host, params))); return; }

  const back = el('a', { class: 'link back-link', href: '#/contracts', text: '← Contrats' });

  // Le PDF est servi par une route authentifiée : on le récupère en blob (Bearer) —
  // un simple <a href> n'enverrait pas le jeton (401).
  async function fetchPdfBlobUrl() {
    const res = await api.downloadRaw(c.id);
    return URL.createObjectURL(await res.blob());
  }
  async function downloadPdf(e) {
    const btn = e.target; btn.disabled = true;
    try {
      const url = await fetchPdfBlobUrl();
      const a = el('a', { attrs: { href: url, download: c.source_filename || 'contrat-' + c.id + '.pdf' } });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (err) { toast('Téléchargement impossible : ' + err.message, 'error'); }
    finally { btn.disabled = false; }
  }

  const viewer = pdfViewer(c, fetchPdfBlobUrl);

  const actions = el('div', { class: 'page-actions' }, [
    c.source_filename ? el('button', { class: 'btn btn-primary', text: 'Visualiser le PDF', onClick: () => viewer.open() }) : null,
    c.source_filename ? el('button', { class: 'btn btn-ghost', text: 'Télécharger', onClick: downloadPdf }) : null,
    c.status !== 'resilie'
      ? el('button', { class: 'btn btn-danger', text: 'Marquer comme résilié', onClick: async (e) => {
          e.target.disabled = true;
          try { await api.markResilie(c.id); toast('Contrat marqué comme résilié.', 'success'); renderContractDetail(host, params); }
          catch (err) { toast(err.message, 'error'); e.target.disabled = false; }
        } })
      : null,
    el('button', { class: 'btn btn-danger', text: 'Supprimer', onClick: async (e) => {
      if (!window.confirm('Supprimer définitivement ce contrat (et son analyse) ?')) return;
      e.target.disabled = true;
      try { await api.deleteContract(c.id); toast('Contrat supprimé.', 'success'); navigate('/contracts'); }
      catch (err) { toast(err.message, 'error'); e.target.disabled = false; }
    } }),
  ]);

  const d = daysUntil(c.cancel_deadline);
  const kfBody = el('div', {});
  function kfReadOnly() {
    mount(kfBody, el('div', { class: 'kv-grid' }, [
      kv('Fournisseur / entité', c.legal_entity || '—'),
      kv('Montant mensuel (MRR)', moneyPrecise(c.amount_mrr)),
      kv('Montant annuel (ARR)', moneyPrecise(c.amount_arr)),
      kv('Récurrence', recurrenceLabel(c.recurrence)),
      kv('Prise d\'effet', dateFR(c.effective_date)),
      kv('Fin de contrat', dateFR(c.contract_end_date)),
      kv('Préavis', c.notice_period_days != null ? c.notice_period_days + ' jours' : '—'),
      kv('Reconduction', c.has_auto_renewal ? 'Tacite' + (c.renewal_months ? ` (${c.renewal_months} mois)` : '') : 'Non'),
      kv('Engagement', c.has_commitment ? 'Oui' : 'Non'),
      kvNode('Échéance de résiliation', el('span', {}, [
        el('span', { text: c.cancel_deadline_label || dateFR(c.cancel_deadline) }),
        d != null ? el('span', { class: 'chip ' + (d <= 30 ? 'chip-warn' : 'chip-muted'), text: d >= 0 ? 'J-' + d : 'dépassé' }) : null,
      ])),
      kvNode('Résiliation effective', el('span', { text: dateFR(c.resiliation_effective_date) })),
    ]));
  }
  kfReadOnly();
  const keyFields = el('section', { class: 'card' }, [
    el('div', { class: 'card-head' }, [
      el('h2', { class: 'card-title', text: 'Champs clés' }),
      el('button', { class: 'btn btn-sm', text: 'Modifier', onClick: () => {
        // Après enregistrement : re-render complet de la fiche (statuts/labels recalculés par le back).
        mount(kfBody, contractEditForm(c, () => renderContractDetail(host, params), kfReadOnly));
      } }),
    ]),
    kfBody,
  ]);

  // Documents annexes
  const annexes = (c.annex_documents || []).length
    ? el('section', { class: 'card' }, [
        el('h2', { class: 'card-title', text: 'Documents' }),
        el('ul', { class: 'doc-list' }, c.annex_documents.map((doc) =>
          el('li', {}, [
            el('span', { text: doc.original_filename || 'Document' }),
            doc.size_bytes ? el('span', { class: 'muted small', text: ' · ' + Math.round(doc.size_bytes / 1024) + ' Ko' }) : null,
          ])
        )),
      ])
    : null;

  // Temps 2 : checklist
  const checklistCard = el('section', { class: 'card card-wide' }, [
    el('h2', { class: 'card-title', text: 'Analyse de conformité' }),
    (c.checklist && Object.keys(c.checklist).length)
      ? renderChecklist(c.checklist)
      : el('p', { class: 'muted', text: 'Aucune analyse de conformité disponible pour ce contrat.' }),
  ]);

  mount(host, el('div', { class: 'page' }, [
    back,
    el('div', { class: 'page-head' }, [
      el('div', {}, [
        el('h1', { class: 'page-title', text: c.title || 'Contrat #' + c.id }),
        el('div', { class: 'page-sub-row' }, [statusBadge(c.status), c.source_filename ? el('span', { class: 'muted small', text: c.source_filename }) : null]),
      ]),
      actions,
    ]),
    viewer.cardEl,
    keyFields,
    annexes,
    qaCard(c),
    checklistCard,
  ]));
}

// Visionneuse PDF intégrée (iframe sur blob URL, chargée au premier affichage).
function pdfViewer(c, fetchPdfBlobUrl) {
  const frameHost = el('div', { class: 'pdf-frame-host' });
  const cardEl = el('section', { class: 'card pdf-card', style: { display: 'none' } }, [
    el('div', { class: 'card-head' }, [
      el('h2', { class: 'card-title', text: c.source_filename || 'Document' }),
      el('button', { class: 'icon-btn', text: '✕', onClick: () => { cardEl.style.display = 'none'; }, attrs: { 'aria-label': 'Fermer l’aperçu' } }),
    ]),
    frameHost,
  ]);
  let loaded = false;
  async function open() {
    const wasHidden = cardEl.style.display === 'none';
    cardEl.style.display = '';
    if (wasHidden) cardEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (loaded) return;
    mount(frameHost, spinner('Chargement du document…'));
    try {
      const url = await fetchPdfBlobUrl();
      mount(frameHost, el('iframe', { class: 'pdf-frame', attrs: { src: url, title: 'Aperçu du contrat' } }));
      loaded = true;
    } catch (err) {
      mount(frameHost, el('p', { class: 'form-error', text: 'Impossible de charger le PDF : ' + err.message }));
    }
  }
  return { cardEl, open };
}

function qaCard(c) {
  const answer = el('div', { class: 'qa-answer', style: { display: 'none' } });
  const input = el('input', { class: 'input', attrs: { placeholder: 'Poser une question sur ce contrat…' } });
  const ask = async () => {
    const q = input.value.trim();
    if (!q) return;
    const bar = thinkingBar(['Lecture du contrat…', 'Recherche de la réponse…', 'Rédaction…'], 25000);
    mount(answer, bar.node); answer.style.display = 'block';
    try { const r = await api.qaAsk(c.id, q); bar.finish(); mount(answer, el('p', { text: (r && (r.answer || r.response)) || 'Pas de réponse.' })); }
    catch (err) { bar.fail('Échec'); mount(answer, el('p', { class: 'form-error', text: err.message })); }
  };
  return el('section', { class: 'card' }, [
    el('h2', { class: 'card-title', text: 'Questions sur le contrat' }),
    el('div', { class: 'qa-row' }, [
      input,
      el('button', { class: 'btn btn-primary', text: 'Demander', onClick: ask }),
    ]),
    answer,
  ]);
}

function kv(k, v) { return el('div', { class: 'kv' }, [el('span', { class: 'kv-k', text: k }), el('span', { class: 'kv-v', text: String(v) })]); }
function kvNode(k, node) { return el('div', { class: 'kv' }, [el('span', { class: 'kv-k', text: k }), el('span', { class: 'kv-v' }, node)]); }
function recurrenceLabel(r) { return ({ monthly: 'Mensuel', quarterly: 'Trimestriel', semiannual: 'Semestriel', annual: 'Annuel', biannual: 'Bisannuel' })[r] || r || '—'; }
