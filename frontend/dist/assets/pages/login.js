// login.js — écran de connexion.
import { el, mount } from '../dom.js?v=2';
import { api, ApiError } from '../api.js?v=2';
import { setSession, getSession } from '../store.js?v=2';

export async function renderLogin(root, onSuccess) {
  if (getSession()) { onSuccess(); return; }

  const errorBox = el('div', { class: 'form-error', style: { display: 'none' } });
  const submitBtn = el('button', { class: 'btn btn-primary btn-block', type: 'submit', text: 'Se connecter' });
  const emailInput = el('input', { class: 'input', type: 'email', name: 'username', attrs: { autocomplete: 'username', required: 'required', placeholder: 'vous@infoclip.fr' } });
  const passInput = el('input', { class: 'input', type: 'password', name: 'password', attrs: { autocomplete: 'current-password', required: 'required', placeholder: '••••••••' } });

  function showError(msg) { errorBox.textContent = msg; errorBox.style.display = 'block'; }

  const form = el('form', {
    class: 'login-form', attrs: { novalidate: 'novalidate' },
    onSubmit: async (e) => {
      e.preventDefault();
      errorBox.style.display = 'none';
      const username = emailInput.value.trim();
      const password = passInput.value;
      if (!username || !password) { showError('Renseignez votre e-mail et votre mot de passe.'); return; }
      submitBtn.disabled = true; submitBtn.textContent = 'Connexion…';
      try {
        const tok = await api.login(username, password);
        setSession(tok.access_token, null);
        let user = null;
        try { user = await api.me(); } catch {}
        setSession(tok.access_token, user);
        onSuccess();
      } catch (err) {
        showError(err instanceof ApiError && err.status === 400 ? 'E-mail ou mot de passe incorrect.' : (err.message || 'Connexion impossible.'));
        submitBtn.disabled = false; submitBtn.textContent = 'Se connecter';
      }
    },
  }, [
    el('label', { class: 'field' }, [el('span', { text: 'Adresse e-mail' }), emailInput]),
    el('label', { class: 'field' }, [el('span', { text: 'Mot de passe' }), passInput]),
    errorBox,
    submitBtn,
  ]);

  mount(root, el('div', { class: 'auth-page' }, [
    el('div', { class: 'auth-card' }, [
      el('div', { class: 'auth-brand' }, [
        el('div', { class: 'brand-mark brand-mark-lg', text: 'IC' }),
        el('h1', { text: 'Gestion de contrats' }),
        el('p', { class: 'muted', text: 'Espace Infoclip — accès sécurisé' }),
      ]),
      form,
      el('p', { class: 'auth-foot muted', text: 'Traitement souverain des données — hébergement on-prem.' }),
    ]),
  ]));
  emailInput.focus();
}
