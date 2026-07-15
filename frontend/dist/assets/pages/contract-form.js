// contract-form.js — formulaire d'édition des champs clés d'un contrat.
// Partagé entre le résultat d'analyse (analyze.js) et la fiche contrat (contract-detail.js).
import { el } from '../dom.js?v=2';
import { api } from '../api.js?v=2';
import { toast } from '../ui.js?v=2';

const RECURRENCES = [
  ['monthly', 'Mensuel'], ['quarterly', 'Trimestriel'], ['semiannual', 'Semestriel'],
  ['annual', 'Annuel'], ['biannual', 'Bisannuel'],
];

function field(label, input) {
  return el('label', { class: 'field' }, [el('span', { text: label }), input]);
}
function numInput(value, step) {
  return el('input', { class: 'input', type: 'number', value: value ?? '', attrs: { step: step || '0.01', min: '0' } });
}
function dateInput(value) {
  return el('input', { class: 'input', type: 'date', value: (value || '').slice(0, 10) });
}

/**
 * c : contrat sérialisé (doit contenir id + champs clés).
 * onSaved(updated) : appelé avec le contrat mis à jour après PUT réussi.
 * onCancel() : optionnel, bouton Annuler.
 */
export function contractEditForm(c, onSaved, onCancel) {
  const fTitle = el('input', { class: 'input', value: c.title || '' });
  const fMrr = numInput(c.amount_mrr);
  const fArr = numInput(c.amount_arr);
  const fRec = el('select', { class: 'input' }, RECURRENCES.map(([k, lbl]) =>
    el('option', { value: k, text: lbl, selected: c.recurrence === k || undefined })));
  const fEff = dateInput(c.effective_date);
  const fDeadline = dateInput(c.cancel_deadline);
  const fNotice = numInput(c.notice_period_days, '1');
  const fRenew = numInput(c.renewal_months, '1');
  const fAuto = el('input', { type: 'checkbox', checked: !!c.has_auto_renewal });

  const saveBtn = el('button', { class: 'btn btn-primary', text: 'Enregistrer', onClick: save });
  async function save() {
    saveBtn.disabled = true;
    const num = (v) => (v === '' || v == null ? null : Number(v));
    const body = {
      title: fTitle.value.trim() || c.title,
      amount_mrr: num(fMrr.value),
      amount_arr: num(fArr.value),
      recurrence: fRec.value,
      effective_date: fEff.value || null,
      cancel_deadline: fDeadline.value || null,
      notice_period_days: num(fNotice.value),
      renewal_months: num(fRenew.value),
      has_auto_renewal: fAuto.checked,
    };
    try {
      const updated = await api.updateContract(c.id, body);
      toast('Contrat mis à jour.', 'success');
      onSaved(updated);
    } catch (err) {
      toast(err.message || 'Enregistrement impossible.', 'error');
      saveBtn.disabled = false;
    }
  }

  return el('div', { class: 'contract-edit' }, [
    el('div', { class: 'edit-grid' }, [
      field('Intitulé', fTitle),
      field('Récurrence', fRec),
      field('Montant mensuel (€)', fMrr),
      field('Montant annuel (€)', fArr),
      field('Prise d’effet', fEff),
      field('Échéance de résiliation', fDeadline),
      field('Préavis (jours)', fNotice),
      field('Reconduction (mois)', fRenew),
      el('label', { class: 'field' }, [
        el('span', { text: 'Reconduction tacite' }),
        el('span', { class: 'check-row' }, [fAuto, el('span', { class: 'muted small', text: 'Renouvellement automatique' })]),
      ]),
    ]),
    el('div', { class: 'modal-actions' }, [
      onCancel ? el('button', { class: 'btn btn-ghost', text: 'Annuler', onClick: onCancel }) : null,
      saveBtn,
    ]),
  ]);
}
