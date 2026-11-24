'use strict';
(function () {
  var KEY = 'mcp-router-token';
  var $ = function (id) { return document.getElementById(id); };
  var token = null, role = null, timer = null;
  try { token = sessionStorage.getItem(KEY); role = sessionStorage.getItem(KEY + '-role'); } catch (e) { /* no storage */ }

  function el(tag, props, kids) {
    var n = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) {
      if (k === 'text') n.textContent = props[k]; else if (k === 'class') n.className = props[k]; else n.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { n.appendChild(c); });
    return n;
  }
  function short(v, n) {
    var s = v == null ? '' : (typeof v === 'string' ? v : JSON.stringify(v));
    return s.length > n ? s.slice(0, n) + '...' : s;
  }
  function when(t) { return t ? new Date(t).toLocaleString() : ''; }
  function summary(r) {
    if (r == null) return '';
    if (r.content && r.content.length) {
      var t = r.content.map(function (c) { return c.text || '[' + c.type + ']'; }).join(' ');
      return short(t, 300);
    }
    return short(r, 300);
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, token ? { Authorization: 'Bearer ' + token } : {}, opts.headers || {});
    return fetch(path, opts).then(function (r) {
      if (r.status === 401 && token) { signOut(); throw new Error('signed out'); }
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.statusText); return j; });
    });
  }

  function show() {
    var on = !!token;
    $('signin').hidden = on; $('app').hidden = !on; $('signout').hidden = !on;
    $('who').textContent = on ? role : '';
  }
  function signOut() {
    token = role = null;
    try { sessionStorage.removeItem(KEY); sessionStorage.removeItem(KEY + '-role'); } catch (e) { /* ignore */ }
    clearInterval(timer); timer = null; show();
  }

  $('signin').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target;
    $('signin-error').textContent = '';
    api('/api/login', { method: 'POST', body: JSON.stringify({ name: f.name.value, password: f.password.value }) })
      .then(function (j) {
        token = j.token; role = j.role; f.password.value = '';
        try { sessionStorage.setItem(KEY, token); sessionStorage.setItem(KEY + '-role', role); } catch (e) { /* ignore */ }
        start();
      })
      .catch(function (e) { $('signin-error').textContent = e.message; });
  });
  $('signout').addEventListener('click', signOut);

  function decide(id, approve, reason, box) {
    api('/api/decide', { method: 'POST', body: JSON.stringify({ action: id, approve: approve, reason: reason }) })
      .then(refresh)
      .catch(function (e) { box.textContent = e.message; });
  }

  function renderWaiting(calls) {
    var box = $('waiting'), w = calls.filter(function (c) { return c.status === 'proposed'; });
    $('waiting-count').textContent = w.length ? '(' + w.length + ')' : '';
    box.replaceChildren();
    if (!w.length) { box.appendChild(el('p', { class: 'muted', text: 'Nothing waits for a decision.' })); return; }
    w.forEach(function (c) {
      var reason = el('input', { class: 'reason', placeholder: 'reason', 'aria-label': 'reason for call ' + c.id });
      var err = el('span', { class: 'error' });
      var yes = el('button', { type: 'button', class: 'primary', text: 'Approve' });
      var no = el('button', { type: 'button', text: 'Reject' });
      yes.addEventListener('click', function () { decide(c.id, true, reason.value, err); });
      no.addEventListener('click', function () { decide(c.id, false, reason.value, err); });
      box.appendChild(el('div', { class: 'card' }, [
        el('div', { class: 'row' }, [el('strong', { text: '#' + c.id + ' ' + c.tool }), el('span', { class: 'muted', text: 'by ' + c.caller + ', ' + when(c.at) })]),
        el('pre', { text: JSON.stringify(c.arguments, null, 2) }),
        el('div', { class: 'row' }, [reason, yes, no, err])
      ]));
    });
  }

  function table(id, heads, rows) {
    var t = $(id);
    t.replaceChildren(el('thead', {}, [el('tr', {}, heads.map(function (h) { return el('th', { text: h }); }))]),
      el('tbody', {}, rows));
  }
  function td(text, cls) { return el('td', cls ? { class: cls, text: text } : { text: text }); }

  function renderCalls(calls) {
    table('calls', ['id', 'tool', 'caller', 'gate', 'status', 'arguments', 'result', 'decided by', 'at', 'done'],
      calls.map(function (c) {
        return el('tr', {}, [td(String(c.id)), td(c.tool), td(c.caller), td(c.gate), td(c.status, c.status),
          el('td', {}, [el('pre', { text: short(c.arguments, 300) })]), td(c.status === 'refused' ? (c.reason || '') : summary(c.result)),
          td(c.decided_by || ''), td(when(c.at)), td(when(c.done_at))]);
      }));
  }
  function renderTools(tools) {
    table('tools', ['name', 'server', 'gate', 'description'], tools.map(function (t) {
      return el('tr', {}, [td(t.name), td(t.server), td(t.gate), td(short(t.description, 200))]);
    }));
  }

  function refresh() {
    if (!token) return;
    Promise.all([api('/api/calls?limit=100'), api('/api/tools')]).then(function (r) {
      renderWaiting(r[0]); renderCalls(r[0]); renderTools(r[1]);
      $('status').textContent = 'Updated ' + new Date().toLocaleTimeString() + '; refreshes every 3 s.';
    }).catch(function (e) { $('status').textContent = 'Could not refresh: ' + e.message; });
  }
  function start() { show(); refresh(); clearInterval(timer); timer = setInterval(refresh, 3000); }

  if (token) start(); else show();
})();
