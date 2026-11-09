// The Workbench API client: PostgREST at /api, with the signed-in person's token. Plugins get it as wb.api.
//
//   await api.get('component', {select: 'id,title', order: 'updated_at.desc', limit: 20})
//   await api.get('component', {...}, {count: true})          -> {rows, total}
//   await api.post('component', {title: 'x'})                  -> the created row
//   await api.patch('component', {id: 'eq.' + id}, {title: 'y'})
//   await api.rpc('decide', {id, approve: true})

const BASE = '/api';
const KEY = 'wb.session';

function load() {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { return null; }
}

export class ApiError extends Error {
  constructor(status, body) {
    super((body && (body.message || body.hint)) || `request failed (${status})`);
    this.status = status;
    this.body = body;
  }
}

export const api = {
  session: load(),
  onSignedOut: () => {},

  signedIn() {
    const s = this.session;
    return Boolean(s && s.token && s.exp * 1000 > Date.now());
  },

  async signIn(name, pass) {
    const r = await fetch(`${BASE}/rpc/login`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name, pass}),
    });
    const body = await r.json().catch(() => null);
    if (!r.ok) throw new ApiError(r.status, body);
    const payload = JSON.parse(atob(body.token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    this.session = {token: body.token, name: body.name, role: body.role, exp: payload.exp};
    try { localStorage.setItem(KEY, JSON.stringify(this.session)); } catch { /* private window */ }
    return this.session;
  },

  signOut() {
    this.session = null;
    try { localStorage.removeItem(KEY); } catch { /* ignore */ }
    this.onSignedOut();
  },

  async request(method, path, {query, body, prefer, count} = {}) {
    const url = new URL(`${BASE}/${path}`, location.origin);
    for (const [k, v] of Object.entries(query || {})) if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
    const headers = {Accept: 'application/json'};
    if (this.session) headers.Authorization = `Bearer ${this.session.token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const prefs = [prefer, count ? 'count=exact' : null].filter(Boolean);
    if (prefs.length) headers.Prefer = prefs.join(', ');
    const r = await fetch(url, {method, headers, body: body === undefined ? undefined : JSON.stringify(body)});
    if (r.status === 401) { this.signOut(); throw new ApiError(401, null); }
    const text = await r.text();
    const data = text ? JSON.parse(text) : null;
    if (!r.ok) throw new ApiError(r.status, data);
    if (count) {
      const range = r.headers.get('Content-Range') || '';
      return {rows: data, total: Number(range.split('/')[1]) || 0};
    }
    return data;
  },

  get(path, query, opts) { return this.request('GET', path, {query, ...opts}); },
  post(path, body) { return this.request('POST', path, {body, prefer: 'return=representation'}).then((r) => r[0]); },
  patch(path, query, body) { return this.request('PATCH', path, {query, body, prefer: 'return=representation'}).then((r) => r[0]); },
  rpc(name, args) { return this.request('POST', `rpc/${name}`, {body: args || {}}); },
  async count(path, query) { return (await this.get(path, {...query, limit: 0}, {count: true})).total; },
};
