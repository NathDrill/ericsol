// checklist.js — rendu de la checklist de conformité (dict imbriqué renvoyé par le LLM).
// Rendu récursif 100% textContent : robuste à une structure inconnue, aucune injection possible.
import { el } from '../dom.js';

const LABELS = {
  duration_echeances: 'Durée & échéances', dates: 'Dates clés',
  effective_date: 'Prise d\'effet', signature_date: 'Signature', anniversary_date: 'Anniversaire',
  initial_term_end_date: 'Fin de période initiale', termination_deadline: 'Date limite de résiliation',
  notice_period: 'Préavis', auto_renewal: 'Reconduction tacite', commitment: 'Engagement',
  pricing: 'Tarification', amount: 'Montant', recurrence: 'Récurrence',
  parties: 'Parties', vendor: 'Fournisseur', client: 'Client',
  obligations: 'Obligations', penalties: 'Pénalités', liability: 'Responsabilité',
  data_protection: 'Protection des données', rgpd: 'RGPD', gdpr: 'RGPD',
  termination: 'Résiliation', renewal: 'Renouvellement', summary: 'Synthèse', notes: 'Remarques',
  risks: 'Points de vigilance', compliance: 'Conformité',
};

function human(key) {
  if (LABELS[key]) return LABELS[key];
  return String(key).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusChip(v) {
  const s = String(v).toLowerCase();
  if (['ok', 'true', 'oui', 'yes', 'conforme', 'present'].includes(s)) return el('span', { class: 'chip chip-ok', text: 'OK' });
  if (['ko', 'false', 'non', 'no', 'manquant', 'absent', 'missing'].includes(s)) return el('span', { class: 'chip chip-warn', text: 'À vérifier' });
  return null;
}

function renderValue(v) {
  if (v == null || v === '') return el('span', { class: 'muted', text: '—' });
  if (typeof v === 'boolean') return el('span', { class: 'chip ' + (v ? 'chip-ok' : 'chip-muted'), text: v ? 'Oui' : 'Non' });
  if (typeof v === 'number') return el('span', { text: String(v) });
  if (typeof v === 'string') {
    const chip = statusChip(v);
    return chip || el('span', { text: v });
  }
  if (Array.isArray(v)) {
    if (!v.length) return el('span', { class: 'muted', text: '—' });
    return el('ul', { class: 'cl-list' }, v.map((it) =>
      el('li', {}, typeof it === 'object' ? renderTree(it) : el('span', { text: String(it) }))
    ));
  }
  if (typeof v === 'object') return renderTree(v);
  return el('span', { text: String(v) });
}

function renderTree(obj) {
  return el('div', { class: 'cl-tree' }, Object.entries(obj).map(([k, v]) =>
    el('div', { class: 'cl-item' }, [
      el('span', { class: 'cl-key', text: human(k) }),
      el('span', { class: 'cl-val' }, renderValue(v)),
    ])
  ));
}

export function renderChecklist(checklist) {
  if (!checklist || typeof checklist !== 'object') return el('p', { class: 'muted', text: 'Aucune donnée.' });
  const entries = Object.entries(checklist);
  return el('div', { class: 'checklist' }, entries.map(([section, content]) =>
    el('section', { class: 'cl-section' }, [
      el('h4', { class: 'cl-section-title', text: human(section) }),
      (content && typeof content === 'object' && !Array.isArray(content))
        ? renderTree(content)
        : renderValue(content),
    ])
  ));
}
