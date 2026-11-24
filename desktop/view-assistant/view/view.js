// The Assistant (Substrate, S-206): the desktop's chat. What the person says is posted to the desktop server, which keeps
// it as a signal the assistant hears; what the assistant says, shows or asks arrives on the feed (a long poll). A
// `show` becomes a button that opens the view, app or claim in its own window (KK.open, else KK.explain for a claim).
(() => {
  let generation = 0;   // render() runs again when the launcher entry is clicked: the older loop stops
  const css = document.createElement('link');
  css.rel = 'stylesheet'; css.href = '/ui/views/view-assistant/view.css';
  document.head.appendChild(css);

  const api = async (kk, path, body) => {
    const r = await fetch('/desktop/api/' + path, {
      method: body ? 'POST' : 'GET',
      headers: { Authorization: 'Bearer ' + kk.token, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(`${r.status} ${(await r.text()) || r.statusText}`);
    return r.json();
  };

  KK.register({
    id: 'view-assistant',
    title: 'Assistant',
    async render(el, kk) {
      const mine = ++generation;
      const me = (await kk.call('whoami')).role;
      el.replaceChildren();
      const box = document.createElement('div'); box.className = 'chat';
      const log = document.createElement('div'); log.className = 'log'; log.setAttribute('aria-live', 'polite');
      const empty = document.createElement('p'); empty.className = 'empty';
      empty.textContent = 'Say something to the assistant. It answers here, and can open things for you.';
      log.append(empty);
      const replying = document.createElement('div'); replying.className = 'replying';
      const form = document.createElement('form');
      const input = document.createElement('textarea');
      input.placeholder = 'Message the assistant (Enter sends, Shift+Enter for a new line)'; input.setAttribute('aria-label', 'Message');
      const send = document.createElement('button'); send.type = 'submit'; send.textContent = 'Send';
      form.append(input, send); box.append(log, replying, form); el.append(box);
      let replyTo = null, after = 0;

      const add = m => {
        empty.remove();
        const d = document.createElement('div');
        d.className = 'msg' + (m.kind === 'message' && m.by === me ? ' mine' : '') + (m.kind === 'ask' ? ' ask' : '');
        d.dataset.id = m.id; d.dataset.kind = m.kind;
        const who = document.createElement('span'); who.className = 'who';
        who.textContent = `${m.by === me ? 'you' : kk.short(m.by)} · ${new Date(m.at).toLocaleTimeString()}`;
        const text = document.createElement('span');
        if (m.kind === 'show') {
          text.textContent = `Shows you: ${m.body.title || m.body.id}`;
          const b = document.createElement('button'); b.type = 'button'; b.textContent = 'Open ' + (m.body.title || m.body.id);
          b.addEventListener('click', () => m.body.kind === 'claim' ? kk.explain(m.body.id)
            : (kk.open ? kk.open(m.body.id) : alertless(`open ${m.body.id} from the launcher`)));
          d.append(who, text, document.createElement('br'), b);
        } else if (m.kind === 'ask') {
          text.textContent = m.body.question;
          const b = document.createElement('button'); b.type = 'button'; b.textContent = 'Answer';
          b.addEventListener('click', () => { replyTo = m.id; replying.textContent = 'Answering: ' + m.body.question; input.focus(); });
          d.append(who, text, document.createElement('br'), b);
        } else {
          text.textContent = m.body.text;
          d.append(who, text);
        }
        log.append(d); log.scrollTop = log.scrollHeight;
      };
      const alertless = t => { replying.textContent = t; };

      form.addEventListener('submit', async ev => {
        ev.preventDefault();
        const t = input.value.trim();
        if (!t) return;
        send.disabled = true;
        try {
          await api(kk, 'post', { text: t, ...(replyTo ? { reply_to: replyTo } : {}) });
          input.value = ''; replyTo = null; replying.textContent = '';
        } catch (e) { replying.textContent = 'Not sent: ' + e.message; }
        send.disabled = false; input.focus();
      });
      input.addEventListener('keydown', ev => {
        if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
      });

      while (mine === generation && el.isConnected && kk.token) {
        try {
          const rows = await api(kk, `feed?after=${after}&wait=20`);
          if (mine !== generation) break;
          for (const m of rows) { add(m); after = Math.max(after, m.id); }
        } catch (e) {
          replying.textContent = 'The chat is not reachable: ' + e.message;
          await new Promise(r => setTimeout(r, 5000));
        }
      }
    },
  });
})();
