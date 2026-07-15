// ask.js — « Poser une question » : chat global sur l'ensemble du portefeuille.
// L'IA (Mistral local) reçoit les données croisées de la base et répond en tenant compte
// de l'historique de conversation. Rendu 100% textContent (jamais d'innerHTML avec données).
import { el, mount, icon } from '../dom.js';
import { api } from '../api.js';
import { pageHeader } from '../ui.js';

// Historique conservé au niveau module : survit aux navigations, pas au rechargement.
const history = [];

const SUGGESTIONS = [
  'Combien dépense-t-on par mois chez Orange Business ?',
  'Quelles sont les prochaines échéances de résiliation ?',
  'Quel est le contrat le plus cher du portefeuille ?',
  'Quels contrats sont en reconduction tacite ?',
];

// Transforme la réponse texte en paragraphes + listes à puces sûrs.
function answerNodes(text) {
  const nodes = [];
  let list = null;
  for (const raw of String(text || '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) { list = null; continue; }
    if (/^[-•*]\s+/.test(line)) {
      if (!list) { list = el('ul', { class: 'msg-list' }); nodes.push(list); }
      list.appendChild(el('li', { text: line.replace(/^[-•*]\s+/, '') }));
    } else {
      list = null;
      nodes.push(el('p', { text: line }));
    }
  }
  return nodes.length ? nodes : [el('p', { text: 'Pas de réponse.' })];
}

export function renderAsk(host) {
  const scroll = el('div', { class: 'chat-scroll', attrs: { 'aria-live': 'polite' } });
  const input = el('input', {
    class: 'input chat-input',
    attrs: { placeholder: 'Posez une question sur vos contrats…', 'aria-label': 'Votre question', autocomplete: 'off' },
  });
  let busy = false;

  function addMsg(role, children) {
    const row = el('div', { class: 'msg msg-' + role }, [
      role === 'ai' ? el('div', { class: 'ai-avatar', text: 'IA' }) : null,
      el('div', { class: 'msg-bubble' }, children),
    ]);
    scroll.appendChild(row);
    scroll.scrollTop = scroll.scrollHeight;
    return row;
  }

  function typingRow() {
    return addMsg('ai', el('div', { class: 'typing' }, [
      el('span', { class: 'typing-dot' }), el('span', { class: 'typing-dot' }), el('span', { class: 'typing-dot' }),
      el('span', { class: 'typing-label', text: 'L’IA croise vos contrats…' }),
    ]));
  }

  const suggestHost = el('div', { class: 'chat-suggest' }, SUGGESTIONS.map((s) =>
    el('button', { class: 'sug-chip', text: s, onClick: () => send(s) })
  ));

  async function send(preset) {
    const question = (typeof preset === 'string' ? preset : input.value).trim();
    if (!question || busy) return;
    busy = true; input.value = '';
    suggestHost.style.display = 'none';
    addMsg('user', el('p', { text: question }));
    const pending = typingRow();
    try {
      const r = await api.qaGlobal(question, history.slice(-8));
      pending.remove();
      const answer = (r && r.answer) || 'Pas de réponse.';
      addMsg('ai', answerNodes(answer));
      history.push({ role: 'user', content: question }, { role: 'assistant', content: answer });
    } catch (err) {
      pending.remove();
      addMsg('ai', el('p', { class: 'msg-error', text: err.message || 'Erreur inattendue.' }));
    } finally {
      busy = false;
      scroll.scrollTop = scroll.scrollHeight;
      input.focus();
    }
  }

  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
  const sendBtn = el('button', { class: 'btn btn-primary btn-send', onClick: () => send(), attrs: { 'aria-label': 'Envoyer' } }, [icon('send', 18)]);

  if (history.length) {
    // Retour sur la page : on rejoue la conversation de la session.
    suggestHost.style.display = 'none';
    for (const turn of history) {
      addMsg(turn.role === 'user' ? 'user' : 'ai',
        turn.role === 'user' ? el('p', { text: turn.content }) : answerNodes(turn.content));
    }
  } else {
    addMsg('ai', el('p', { text: 'Bonjour ! Posez-moi une question sur votre portefeuille : je croise les données de tous vos contrats — montants, échéances, préavis, reconductions, fournisseurs…' }));
  }

  mount(host, el('div', { class: 'page page-chat' }, [
    pageHeader('Poser une question', 'L’assistant IA croise les données de tous vos contrats pour vous répondre.'),
    el('section', { class: 'card chat-card' }, [
      scroll,
      suggestHost,
      el('div', { class: 'composer' }, [input, sendBtn]),
    ]),
  ]));
  input.focus();
}
