// The shell: sign-in, the sidebar, the workspace (Dockview), the inspector, the command palette, and the `wb`
// object every plugin gets. Plugins are listed in the page as <meta name="wb-plugin" content="...js"> (the page
// is a Caddy template that finds them, see index.html); each module's default export is called with `wb`
// before Alpine starts, so the components and views it registers exist when the page is drawn.

import Alpine from '../vendor/alpine-csp-3.17.5.esm.min.js';
import {createDockview, themeDark, themeLight} from '../vendor/dockview-core-8.6.2.esm.min.js';
import {api} from './api.js';
import {createRegistry} from './registry.js';

const registry = createRegistry();
const panels = new Map();          // panel id -> {params, api, component}
const listeners = new Map();       // event -> Set(fn)
let dock = null;
let restoring = false;

const SECTIONS = ['Workspace', 'Content', 'Apps', 'System'];

function emit(event, detail) { (listeners.get(event) || []).forEach((fn) => { try { fn(detail); } catch (e) { console.error(e); } }); }
function stored(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
function store(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private window */ } }
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ------------------------------------------------------------------ the object plugins get
const wb = {
  api, Alpine, registry,
  version: '0.1.0',
  pluginApi: '1',

  view: (d) => registry.add('view', d),
  widget: (d) => registry.add('widget', d),
  inspector: (d) => registry.add('inspector', d),
  field: (d) => registry.add('field', d),
  command: (d) => registry.add('command', d),
  menu: (d) => registry.add('menu', d),
  app: (d) => registry.add('app', d),
  data: (name, factory) => Alpine.data(name, factory),

  on(event, fn) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event).add(fn);
    return () => listeners.get(event).delete(fn);
  },
  emit,

  get state() { return Alpine.store('wb'); },
  get user() { return api.session; },
  canEdit() { return ['wb_editor', 'wb_owner'].includes(api.session?.role); },
  type(id) { return Alpine.store('wb').types.find((t) => t.id === id); },

  // What the current view is about; inspectors follow it.
  select(selection) {
    Alpine.store('wb').selection = selection || null;
    emit('selection', selection);
  },

  // Open a view as a tab. A view's key(params) names the tab, so opening the same thing again focuses it.
  // where: 'tab' (default, in the active group), 'right', 'below', 'float'.
  open(viewId, params = {}, {where = 'tab', title} = {}) {
    const view = registry.get('view', viewId);
    if (!view) return wb.notify(`No view "${viewId}": its plugin is not installed`, 'error');
    if (!dock) return null;
    const id = view.key ? view.key(params) : viewId + (Object.keys(params).length ? ':' + new URLSearchParams(params) : '');
    const existing = dock.getPanel(id);
    if (existing) { existing.api.setActive(); return existing; }
    const options = {id, component: viewId, params, title: title || (view.title ? view.title(params) : viewId)};
    const active = dock.activePanel;
    if (where === 'float') options.floating = {width: 640, height: 480};
    else if ((where === 'right' || where === 'below') && active) options.position = {referencePanel: active.id, direction: where};
    return dock.addPanel(options);
  },

  panelOf(el) {
    const host = el && el.closest('[data-panel]');
    if (!host) return null;
    const id = host.dataset.panel;
    const p = panels.get(id);
    return p && {
      id, params: p.params,
      setTitle: (t) => p.api.setTitle(t),
      close: () => p.api.close(),
    };
  },

  float() { const p = dock?.activePanel; if (p) dock.addFloatingGroup(p); },
  popout() { const p = dock?.activePanel; if (p && dock.addPopoutGroup) dock.addPopoutGroup(p); },
  split(direction = 'right') {
    const p = dock?.activePanel;
    const known = p && panels.get(p.id);
    if (known) dock.addPanel({id: p.id + ':' + Date.now(), component: known.component, params: known.params,
                              title: p.title, position: {referencePanel: p.id, direction}});
  },
  resetLayout() { dock?.clear(); wb.open('dashboard'); },
  toggleTheme() { setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'); },
  toggleInspector() { const s = Alpine.store('wb'); s.inspectorOpen = !s.inspectorOpen; store('wb.inspector.open', s.inspectorOpen); },

  notify(message, kind = 'info') {
    const s = Alpine.store('wb');
    const n = {id: Date.now() + Math.random(), message, kind};
    s.toasts.push(n);
    setTimeout(() => { s.toasts = s.toasts.filter((t) => t.id !== n.id); }, kind === 'error' ? 8000 : 4000);
    return null;
  },

  // A view's template by id, cloned; for plugins that build views from parts.
  template(id) {
    const t = document.getElementById(id);
    return t ? t.content.cloneNode(true) : null;
  },
};
window.wb = wb;

// ------------------------------------------------------------------ the workspace
function renderer(panelId, component) {
  const element = document.createElement('div');
  element.className = 'wb-view';
  let cleanup = null;
  return {
    element,
    init(p) {
      panels.set(panelId, {params: p.params || {}, api: p.api, component});
      element.dataset.panel = panelId;
      const view = registry.get('view', component);
      if (!view) {
        element.append(Object.assign(document.createElement('p'), {className: 'wb-empty',
          textContent: `This tab shows "${component}", which no installed plugin provides.`}));
        return;
      }
      if (view.template) {
        const tpl = document.getElementById(view.template);
        if (tpl) element.append(tpl.content.cloneNode(true));
        Alpine.initTree(element);
      } else if (view.mount) {
        cleanup = view.mount(element, {...wb, panel: wb.panelOf(element)}) || null;
      }
    },
    dispose() {
      Alpine.destroyTree(element);
      if (typeof cleanup === 'function') cleanup();
      panels.delete(panelId);
    },
  };
}

function watermark() {
  const element = document.createElement('div');
  element.className = 'wb-watermark';
  element.innerHTML = '<p>Nothing open.</p><p class="wb-muted">Pick something in the sidebar, or press <kbd>Ctrl</kbd> <kbd>K</kbd>.</p>';
  return {element, init() {}};
}

function layoutKey() { return `wb.layout.${api.session?.name || 'anon'}`; }

function mountWorkspace(el) {
  dock = createDockview(el, {
    theme: document.documentElement.dataset.theme === 'dark' ? themeDark : themeLight,
    popoutUrl: '/wb/popout.html',
    createComponent: ({id, name}) => renderer(id, name),
    createWatermarkComponent: watermark,
  });
  const save = debounce(() => { if (!restoring) store(layoutKey(), dock.toJSON()); }, 400);
  dock.onDidLayoutChange(save);
  dock.onDidActivePanelChange((panel) => {
    if (restoring) return;
    const p = panel && panels.get(panel.id);
    if (panel && p) {
      const q = new URLSearchParams({view: p.component, ...p.params});
      history.replaceState(null, '', '#' + q);
    }
    if (!panel) wb.select(null);
  });
  const saved = stored(layoutKey(), null);
  if (saved) {
    restoring = true;
    try { dock.fromJSON(saved); } catch (e) { console.warn('layout not restored', e); dock.clear(); }
    restoring = false;
  }
  route();
  if (!dock.panels.length) wb.open('dashboard');
}

// #view=item&type=component&id=... opens that view (links and bookmarks).
function route() {
  const q = new URLSearchParams(location.hash.slice(1));
  const view = q.get('view');
  if (!view) return;
  q.delete('view');
  wb.open(view, Object.fromEntries(q));
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  store('wb.theme', theme);
  dock?.updateOptions({theme: theme === 'dark' ? themeDark : themeLight});
}

// ------------------------------------------------------------------ live updates
// The server relays Postgres's NOTIFY as Server-Sent Events, behind the same token PostgREST checks. fetch()
// rather than EventSource, so the token travels in a header and never in a URL. Events name what changed
// ({kind: item|decision|run, type, id, op, author}); views refetch through the API under the person's own token.
let stopEvents = null;
async function subscribe() {
  if (stopEvents || !api.signedIn()) return;
  const ctl = new AbortController();
  stopEvents = () => ctl.abort();
  const s = Alpine.store('wb');
  try {
    const r = await fetch('/wb/api/events', {headers: {Authorization: `Bearer ${api.session.token}`, Accept: 'text/event-stream'}, signal: ctl.signal});
    if (!r.ok || !r.body) throw new Error(`events: ${r.status}`);
    s.live = true;
    const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
    let buf = '';
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += value;
      let at;
      while ((at = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, at); buf = buf.slice(at + 2);
        let event = 'message'; let data = '';
        for (const line of chunk.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim();
          else if (line.startsWith('data:')) data += line.slice(5).trim();
        }
        if (event === 'change') { try { emit('change', JSON.parse(data)); } catch { /* ignore a bad line */ } }
        if (event === 'expired') { api.signOut(); return; }
      }
    }
  } catch (e) {
    if (ctl.signal.aborted) return;
  } finally {
    s.live = false;
    stopEvents = null;
  }
  if (api.signedIn()) setTimeout(subscribe, 3000);
}
function unsubscribe() { if (stopEvents) stopEvents(); stopEvents = null; }

// Debounced: many writes in one run arrive as one refresh. fn(events) gets the events since the last call.
wb.onChange = (match, fn, ms = 300) => {
  let pending = [];
  const flush = debounce(() => { const evs = pending; pending = []; fn(evs); }, ms);
  return wb.on('change', (e) => { if (match(e)) { pending.push(e); flush(); } });
};

// ------------------------------------------------------------------ the page's own components
Alpine.store('wb', {
  signedIn: api.signedIn(),
  types: [],
  selection: null,
  toasts: [],
  navCollapsed: stored('wb.nav.collapsed', false),
  inspectorOpen: stored('wb.inspector.open', true),
  paletteOpen: false,
  live: false,
  badges: {},          // menu entry badge name -> a count (plugins set them)
});

Alpine.data('shell', () => ({
  name: '', pass: '', error: '', busy: false,

  init() {
    api.onSignedOut = () => { Alpine.store('wb').signedIn = false; };
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); this.togglePalette(); }
      if (e.key === 'Escape') Alpine.store('wb').paletteOpen = false;
    });
    window.addEventListener('hashchange', route);
    if (api.signedIn()) this.start();
  },

  async signIn() {
    this.busy = true; this.error = '';
    try {
      await api.signIn(this.name.trim(), this.pass);
      this.pass = '';
      Alpine.store('wb').signedIn = true;
      await this.start();
    } catch (e) {
      this.error = e.status === 403 ? 'That name and password were not accepted.' : `Could not sign in: ${e.message}`;
    } finally { this.busy = false; }
  },

  async start() {
    try {
      Alpine.store('wb').types = await api.get('content_types', {order: 'label.asc'});
    } catch (e) { wb.notify(`Could not load content types: ${e.message}`, 'error'); }
    await this.$nextTick();
    if (!dock) mountWorkspace(this.$refs.workspace);
    subscribe();
    emit('signedin', api.session);
  },

  signOut() {
    unsubscribe();
    dock?.dispose?.(); dock = null; panels.clear();
    api.signOut();
  },

  get signedIn() { return Alpine.store('wb').signedIn; },
  get who() { return api.session ? api.session.name : ''; },
  get role() { return api.session ? api.session.role.replace('wb_', '') : ''; },
  get navCollapsed() { return Alpine.store('wb').navCollapsed; },
  get inspectorOpen() { return Alpine.store('wb').inspectorOpen; },
  get toasts() { return Alpine.store('wb').toasts; },
  get isDark() { return document.documentElement.dataset.theme === 'dark'; },
  get live() { return Alpine.store('wb').live; },

  toggleNav() { const s = Alpine.store('wb'); s.navCollapsed = !s.navCollapsed; store('wb.nav.collapsed', s.navCollapsed); },
  toggleInspector() { wb.toggleInspector(); },
  togglePalette() { const s = Alpine.store('wb'); s.paletteOpen = !s.paletteOpen; },
  toggleTheme() { wb.toggleTheme(); },

  // The sidebar: plugin menu entries, one entry per content type, and the apps, grouped by section.
  get sections() {
    const types = Alpine.store('wb').types;
    const entries = [
      ...registry.list('menu'),
      ...types.map((t) => ({id: 'type:' + t.id, section: 'Content', title: t.label, icon: 'doc', open: ['list', {type: t.id}], order: 50})),
      ...registry.list('app').map((a) => ({id: 'app:' + a.id, section: 'Apps', title: a.title, icon: a.icon || 'app', app: a, order: a.order ?? 50})),
    ];
    return SECTIONS.map((name) => ({name, entries: entries.filter((e) => e.section === name).sort((a, b) => (a.order ?? 50) - (b.order ?? 50))}))
      .filter((s) => s.entries.length);
  },

  badge(e) { return e.badge ? (Alpine.store('wb').badges[e.badge] || 0) : 0; },

  go(entry) {
    if (entry.app) return launch(entry.app);
    const [view, params] = entry.open;
    wb.open(view, params || {});
  },

  // The inspector: the sections whose applies() matches the selection.
  get inspectors() {
    const sel = Alpine.store('wb').selection;
    return registry.list('inspector').filter((i) => !i.applies || i.applies(sel));
  },
  get hasSelection() { return Boolean(Alpine.store('wb').selection); },
  dismiss(id) { const s = Alpine.store('wb'); s.toasts = s.toasts.filter((t) => t.id !== id); },
}));

// An inspector section: renders its template, or calls mount, into its own element.
Alpine.data('inspectorSection', () => ({
  cleanup: null,
  init() {
    const def = registry.get('inspector', this.$el.closest('[data-inspector]')?.dataset.inspector);
    if (!def) return;
    const body = document.createElement('div');       // fresh, so Alpine initialises it exactly once
    this.$el.append(body);
    if (def.template) {
      const tpl = document.getElementById(def.template);
      if (tpl) { body.append(tpl.content.cloneNode(true)); Alpine.initTree(body); }
    } else if (def.mount) {
      this.cleanup = def.mount(body, wb);
    }
  },
  destroy() { if (typeof this.cleanup === 'function') this.cleanup(); },
}));

// Apps: another web UI in a tab, a floating window, or the browser's own window when it refuses to be framed.
function launch(app) {
  if (app.embed === 'window') {
    window.open(app.url, `wb-app-${app.id}`, 'noopener');
    return;
  }
  wb.open('app', {app: app.id}, {title: app.title});
}

Alpine.data('appFrame', () => ({
  app: null,
  init() {
    const panel = wb.panelOf(this.$el);
    this.app = registry.get('app', panel?.params.app) || null;
  },
  get url() { return this.app ? this.app.url : 'about:blank'; },
  get title() { return this.app ? this.app.title : 'Unknown app'; },
  reload() { const f = this.$refs.frame; if (f) f.src = this.url; },
  external() { if (this.app) window.open(this.app.url, `wb-app-${this.app.id}`, 'noopener'); },
}));

// The command palette: commands, then items whose title matches, across every content type.
Alpine.data('palette', () => ({
  q: '', results: [], index: 0, seq: 0,
  get open() { return Alpine.store('wb').paletteOpen; },
  init() {
    // focus once x-show has made the overlay visible: a hidden input cannot take focus, and $nextTick is too soon
    this.$watch('open', (v) => { if (v) { this.q = ''; this.search(); requestAnimationFrame(() => requestAnimationFrame(() => this.$refs.input?.focus())); } });
    this.$watch('q', debounce(() => this.search(), 150));
  },
  close() { Alpine.store('wb').paletteOpen = false; },
  async search() {
    const q = this.q.trim().toLowerCase();
    const seq = ++this.seq;
    const cmds = registry.list('command').filter((c) => (!c.when || c.when(wb)) && c.title.toLowerCase().includes(q))
      .slice(0, 8).map((c) => ({id: 'cmd:' + c.id, label: c.title, hint: 'Command', run: () => c.run(wb)}));
    this.results = cmds; this.index = 0;
    if (q.length < 2) return;
    // recall: full-text over every type and every claim's quote (/api/rpc/search), best hit per item
    const hits = await api.rpc('search', {q, lim: 12}).catch(() => []);
    const best = new Map();
    for (const h of hits) { const k = `${h.type}:${h.id}`; if (!best.has(k) || best.get(k).rank < h.rank) best.set(k, h); }
    const titles = new Map(hits.filter((h) => h.title).map((h) => [`${h.type}:${h.id}`, h.title]));
    const found = [...best.values()].sort((a, b) => b.rank - a.rank).slice(0, 12).map((h) => ({
      id: `${h.type}:${h.id}`, label: titles.get(`${h.type}:${h.id}`) || h.snippet.replace(/<\/?b>/g, ''),
      hint: (wb.type(h.type)?.label || h.type) + (h.via.startsWith('quote') ? ' · quoted' : ''),
      snippet: h.snippet.replace(/<\/?b>/g, ''),
      run: () => wb.open('item', {type: h.type, id: h.id}),
    }));
    if (seq === this.seq) this.results = [...cmds, ...found];
  },
  move(d) { if (this.results.length) this.index = (this.index + d + this.results.length) % this.results.length; },
  choose(i) {
    const r = this.results[i ?? this.index];
    if (!r) return;
    this.close();
    r.run();
  },
  isActive(i) { return i === this.index; },
}));

// ------------------------------------------------------------------ boot
setTheme(stored('wb.theme', matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
const modules = [...document.querySelectorAll('meta[name="wb-plugin"]')].map((m) => m.content);
for (const src of modules) {
  try {
    const mod = await import(src);
    const plugin = mod.default;
    if (typeof plugin === 'function') await plugin(wb);
  } catch (e) {
    console.error(`plugin ${src} failed to load`, e);
    queueMicrotask(() => wb.notify(`A plugin failed to load: ${src}`, 'error'));
  }
}
window.Alpine = Alpine;
Alpine.start();
