// analyze.js — upload d'un PDF + analyse par le LLM on-prem, AFFICHAGE EN 2 TEMPS :
//   temps 1 : champs clés (fournisseur, montants, dates, préavis…) dès qu'ils sont disponibles,
//   temps 2 : checklist de conformité (12 points) qui s'affiche ensuite, sans clic.
// Le rendu est piloté par renderKeyFields() puis renderChecklist(), séparés, pour que
// le jour où le back renvoie les deux phases séparément, ce soit un simple branchement.
import { el, mount, clear, money, dateFR } from '../dom.js?v=2';
import { api } from '../api.js?v=2';
import { toast, spinner, thinkingBar } from '../ui.js?v=2';
import { renderChecklist } from './checklist.js?v=2';
import { contractEditForm } from './contract-form.js?v=2';

const MAX_MB = 25;

export function openAnalyzePanel(onDone) {
  const body = el('div', { class: 'modal-body' });
  const overlay = el('div', { class: 'modal-overlay', onClick: (e) => { if (e.target === overlay) close(); } }, [
    el('div', { class: 'modal', attrs: { role: 'dialog', 'aria-modal': 'true' } }, [
      el('div', { class: 'modal-head' }, [
        el('h2', { class: 'modal-title', text: 'Analyser un contrat' }),
        el('button', { class: 'icon-btn', attrs: { 'aria-label': 'Fermer' }, text: '✕', onClick: () => close() }),
      ]),
      body,
    ]),
  ]);
  function close() { overlay.remove(); document.removeEventListener('keydown', onKey); if (onDone) onDone(); }
  function onKey(e) { if (e.key === 'Escape') close(); }
  document.addEventListener('keydown', onKey);
  document.body.appendChild(overlay);

  showPicker(body, close);
}

function showPicker(body, close) {
  const fileInput = el('input', { class: 'input', type: 'file', attrs: { accept: 'application/pdf,.pdf' } });
  const startBtn = el('button', { class: 'btn btn-primary', text: 'Lancer l\'analyse', onClick: () => {
    const f = fileInput.files && fileInput.files[0];
    if (!f) { toast('Sélectionnez un fichier PDF.', 'warn'); return; }
    if (f.type && f.type !== 'application/pdf' && !/\.pdf$/i.test(f.name)) { toast('Format non supporté : PDF requis.', 'error'); return; }
    if (f.size > MAX_MB * 1024 * 1024) { toast(`Fichier trop volumineux (max ${MAX_MB} Mo).`, 'error'); return; }
    runAnalysis(body, f);
  } });

  mount(body, el('div', { class: 'analyze-picker' }, [
    el('p', { class: 'muted', text: 'Déposez un contrat au format PDF. L\'extraction est réalisée par le modèle local (aucune donnée ne quitte l\'infrastructure).' }),
    el('label', { class: 'field' }, [el('span', { text: 'Fichier PDF' }), fileInput]),
    el('div', { class: 'modal-actions' }, [
      el('button', { class: 'btn btn-ghost', text: 'Annuler', onClick: close }),
      startBtn,
    ]),
  ]));
}

async function runAnalysis(body, file) {
  // Temps 0 : barre de progression (l'IA « réfléchit »). Durée estimée ~75s (Mistral local sur L4).
  const bar = thinkingBar([
    'Lecture du document…', 'Extraction des champs clés…',
    'Analyse de conformité (12 points)…', 'Mise en forme des résultats…',
  ], 85000);
  const result = el('div', { class: 'analyze-stages' });
  mount(body, el('div', { class: 'analyze-result' }, [
    el('div', { class: 'analyze-file' }, [el('strong', { text: file.name })]),
    bar.node,
    result,
  ]));

  let data;
  try { data = await api.analyzePdf(file); }
  catch (err) { bar.fail('Analyse impossible'); mount(result, el('div', { class: 'form-error', text: err.message || 'Analyse impossible.' })); return; }
  bar.finish();

  const norm = normalize(data);
  const stage1 = el('div', { class: 'analyze-stage' });
  const stage2 = el('div', { class: 'analyze-stage' });
  mount(result, el('div', {}, [stage1, stage2]));

  // Temps 1 : champs clés (immédiat)
  renderKeyFields(stage1, norm);
  // Temps 2 : checklist (affichage différé, sans clic)
  mount(stage2, spinner('Affichage de l\'analyse de conformité…'));
  setTimeout(() => {
    if (norm.checklist && Object.keys(norm.checklist).length) {
      mount(stage2, el('div', {}, [el('h3', { class: 'section-title', text: 'Conformité & points de vigilance' }), renderChecklist(norm.checklist)]));
    } else {
      mount(stage2, el('p', { class: 'muted', text: 'Aucune checklist retournée pour ce document.' }));
    }
  }, 500);
}

// Normalise la réponse (tolère plusieurs formes possibles du back).
function normalize(data) {
  const c = data.contract || data.result || data;
  return {
    title: c.title || c.name || data.title || '—',
    vendor: c.vendor_name || c.legal_entity || c.vendor || '',
    amount_mrr: c.amount_mrr, amount_arr: c.amount_arr,
    recurrence: c.recurrence, effective_date: c.effective_date,
    notice_period_days: c.notice_period_days, renewal_months: c.renewal_months,
    has_auto_renewal: c.has_auto_renewal, cancel_deadline: c.cancel_deadline,
    checklist: c.checklist || data.checklist || null,
    id: c.id || data.id || null,
  };
}

function renderKeyFields(hostEl, n) {
  const rows = [
    ['Intitulé', n.title],
    ['Fournisseur / entité', n.vendor || '—'],
    ['Montant mensuel', n.amount_mrr != null ? money(n.amount_mrr) : '—'],
    ['Montant annuel', n.amount_arr != null ? money(n.amount_arr) : '—'],
    ['Prise d\'effet', dateFR(n.effective_date)],
    ['Préavis', n.notice_period_days != null ? n.notice_period_days + ' jours' : '—'],
    ['Reconduction', n.has_auto_renewal ? 'Tacite' + (n.renewal_months ? ` (${n.renewal_months} mois)` : '') : 'Non'],
    ['Échéance de résiliation', dateFR(n.cancel_deadline)],
  ];
  // Le contrat est déjà créé en base : les champs restent modifiables par le client.
  const editBtn = n.id != null ? el('button', {
    class: 'btn btn-sm', text: 'Modifier les champs',
    onClick: () => mount(hostEl, el('div', {}, [
      el('h3', { class: 'section-title', text: 'Modifier les champs' }),
      contractEditForm(n, (updated) => renderKeyFields(hostEl, normalize(updated)), () => renderKeyFields(hostEl, n)),
    ])),
  }) : null;
  mount(hostEl, el('div', {}, [
    el('div', { class: 'card-head' }, [el('h3', { class: 'section-title', text: 'Champs clés extraits' }), editBtn]),
    el('div', { class: 'kv-grid' }, rows.map(([k, v]) =>
      el('div', { class: 'kv' }, [el('span', { class: 'kv-k', text: k }), el('span', { class: 'kv-v', text: String(v) })])
    )),
  ]));
}
