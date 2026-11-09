// Workbench's own screens, registered through the same calls any plugin uses (js/registry.js). Their markup is
// in core/views.html. Alpine's CSP build allows no assignments to nested properties and no globals inside
// attributes, so the components below do that work in methods.

const ago = (iso) => {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now';
  for (const [n, unit] of [[86400 * 365, 'y'], [86400 * 30, 'mo'], [86400, 'd'], [3600, 'h'], [60, 'm']]) {
    if (s >= n) return `${Math.floor(s / n)}${unit} ago`;
  }
  return '';
};
const when = (iso) => (iso ? new Date(iso).toLocaleString() : '');
const show = (v) => {
  if (v === null || v === undefined || v === '') return '—';
  if (Array.isArray(v)) return v.join(', ');
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
};
const FRAME = ['id', 'slug', 'title', 'created_at', 'updated_at', 'created_by', 'updated_by'];

// The editor for one property: the registered field with the highest score for it.
function fieldFor(wb, prop) {
  let best = null; let score = 0;
  for (const f of wb.registry.list('field')) {
    const s = f.match(prop) || 0;
    if (s > score) { best = f; score = s; }
  }
  return best;
}

export default function core(wb) {
  wb.format = {ago, when, show};

  // ---------------------------------------------------------------- fields (by JSON Schema type and format)
  const kind = (id, match) => wb.field({id, kind: id, match});
  kind('text', (p) => (p.type === 'string' ? 1 : 0));
  kind('textarea', (p) => (p.type === 'string' && (p.format === 'markdown' || p['x-widget'] === 'textarea' || /description|body|notes?/i.test(p.name || '')) ? 2 : 0));
  kind('number', (p) => (p.type === 'number' || p.type === 'integer' ? 1 : 0));
  kind('boolean', (p) => (p.type === 'boolean' ? 1 : 0));
  kind('datetime', (p) => (p.type === 'string' && p.format === 'date-time' ? 2 : 0));
  kind('date', (p) => (p.type === 'string' && p.format === 'date' ? 2 : 0));
  kind('tags', (p) => (p.type === 'array' && (!p.items || p.items.type === 'string') ? 1 : 0));
  kind('json', (p) => (p.type === 'object' || p.type === 'array' ? 0.5 : 0.1));

  // ---------------------------------------------------------------- views
  wb.view({id: 'dashboard', title: () => 'Dashboard', template: 'wb-tpl-dashboard', key: () => 'dashboard'});
  wb.view({id: 'list', title: (p) => wb.type(p.type)?.label || p.type, template: 'wb-tpl-list', key: (p) => `list:${p.type}`});
  wb.view({id: 'item', title: (p) => (p.id === 'new' ? `New ${wb.type(p.type)?.label || p.type}` : '…'),
           template: 'wb-tpl-item', key: (p) => (p.id === 'new' ? `item:${p.type}:new:${Date.now()}` : `item:${p.type}:${p.id}`)});
  wb.view({id: 'claims', title: () => 'Claims', template: 'wb-tpl-claims', key: () => 'claims'});
  wb.view({id: 'review', title: () => 'Review', template: 'wb-tpl-review', key: () => 'review'});
  wb.view({id: 'types', title: () => 'Content types', template: 'wb-tpl-types', key: () => 'types'});
  wb.view({id: 'extractors', title: () => 'Extractors', template: 'wb-tpl-extractors', key: () => 'extractors'});
  wb.view({id: 'app', title: (p) => wb.registry.get('app', p.app)?.title || 'App', template: 'wb-tpl-app', key: (p) => `app:${p.app}`});

  // ---------------------------------------------------------------- sidebar
  wb.menu({id: 'dashboard', section: 'Workspace', title: 'Dashboard', icon: 'home', open: ['dashboard'], order: 1});
  wb.menu({id: 'review', section: 'Review', title: 'Decisions', icon: 'check', open: ['review'], order: 1});
  wb.menu({id: 'claims', section: 'Review', title: 'Claims', icon: 'quote', open: ['claims'], order: 2});
  wb.menu({id: 'types', section: 'System', title: 'Content types', icon: 'schema', open: ['types'], order: 1});
  wb.menu({id: 'extractors', section: 'System', title: 'Extractors', icon: 'refresh', open: ['extractors'], order: 2});

  // ---------------------------------------------------------------- inspector
  wb.inspector({id: 'provenance', title: 'Where this came from', template: 'wb-tpl-provenance', order: 1,
                applies: (s) => Boolean(s && s.type && s.id && s.id !== 'new')});
  wb.inspector({id: 'item-info', title: 'Item', template: 'wb-tpl-item-info', order: 2,
                applies: (s) => Boolean(s && s.type && s.id && s.id !== 'new')});

  // ---------------------------------------------------------------- dashboard widgets
  wb.widget({id: 'content', title: 'Content', size: 'm', template: 'wb-tpl-w-content', order: 1});
  wb.widget({id: 'recent', title: 'Recent changes', size: 'l', template: 'wb-tpl-w-recent', order: 2});
  wb.widget({id: 'decisions', title: 'Waiting for a decision', size: 'm', template: 'wb-tpl-w-decisions', order: 3});
  wb.widget({id: 'apps', title: 'Apps', size: 's', template: 'wb-tpl-w-apps', order: 4, when: () => wb.registry.list('app').length > 0});

  // ---------------------------------------------------------------- commands
  const cmd = (id, title, run, whenFn) => wb.command({id, title, run, when: whenFn});
  cmd('dashboard', 'Open the dashboard', () => wb.open('dashboard'));
  cmd('claims', 'Open claims', () => wb.open('claims'));
  cmd('review', 'Open the review lane', () => wb.open('review'));
  cmd('types', 'Open content types', () => wb.open('types'));
  cmd('extractors', 'Open extractors', () => wb.open('extractors'));
  cmd('split-right', 'Split the active tab to the right', () => wb.split('right'));
  cmd('split-below', 'Split the active tab below', () => wb.split('below'));
  cmd('float', 'Float the active tab', () => wb.float());
  cmd('popout', 'Pop the active tab out into its own window', () => wb.popout());
  cmd('reset-layout', 'Reset the layout', () => wb.resetLayout());
  cmd('theme', 'Switch between light and dark', () => wb.toggleTheme());
  cmd('inspector', 'Show or hide the inspector', () => wb.toggleInspector());
  wb.on('signedin', () => {
    for (const t of wb.state.types) {
      cmd(`new:${t.id}`, `New ${t.label}`, () => wb.open('item', {type: t.id, id: 'new'}), () => wb.canEdit());
      cmd(`list:${t.id}`, `List ${t.label}`, () => wb.open('list', {type: t.id}));
    }
  });

  // ---------------------------------------------------------------- components
  wb.data('dashboard', () => ({
    get widgets() { return wb.registry.list('widget').filter((w) => !w.when || w.when(wb)); },
    sizeClass(w) { return 'wb-card wb-size-' + (w.size || 'm'); },
  }));

  // One dashboard card: its widget's template, or its mount function.
  wb.data('widgetCard', () => ({
    cleanup: null,
    init() {
      const def = wb.registry.get('widget', this.$el.closest('[data-widget]')?.dataset.widget);
      if (!def) return;
      const body = document.createElement('div');     // fresh, so Alpine initialises it exactly once
      this.$el.append(body);
      if (def.template) { const n = wb.template(def.template); if (n) { body.append(n); wb.Alpine.initTree(body); } }
      else if (def.mount) this.cleanup = def.mount(body, wb);
    },
    destroy() { if (typeof this.cleanup === 'function') this.cleanup(); },
  }));

  wb.data('contentWidget', () => ({
    rows: [],
    async init() { await this.load(); this.off = wb.onChange((e) => e.kind === 'item' && e.op === 'insert', () => this.load(), 800); },
    destroy() { this.off && this.off(); },
    async load() {
      this.rows = await Promise.all(wb.state.types.map(async (t) => ({id: t.id, label: t.label, n: await wb.api.count(t.id).catch(() => '?')})));
    },
    open(r) { wb.open('list', {type: r.id}); },
  }));

  wb.data('recentWidget', () => ({
    rows: [], loaded: false,
    init() { this.load(); this.off = wb.onChange((e) => e.kind === 'item', () => this.load(), 600); },
    destroy() { this.off && this.off(); },
    async load() {
      const claims = await wb.api.get('claims', {select: 'subject_type,subject_id,field,value,author,observed_at', order: 'observed_at.desc', limit: 12}).catch(() => []);
      this.rows = claims.map((c, i) => ({...c, key: i}));
      this.loaded = true;
    },
    label(c) { return `${wb.type(c.subject_type)?.label || c.subject_type} · ${c.field}`; },
    value(c) { return show(c.value); },
    ago(c) { return ago(c.observed_at); },
    open(c) { wb.open('item', {type: c.subject_type, id: c.subject_id}); },
  }));

  wb.data('decisionsWidget', () => ({
    n: null,
    init() { this.load(); this.off = wb.onChange((e) => e.kind === 'decision', () => this.load()); },
    destroy() { this.off && this.off(); },
    async load() { this.n = await wb.api.count('decisions', {status: 'eq.open'}).catch(() => null); },
    get text() { return this.n === null ? '…' : this.n === 0 ? 'Nothing is waiting.' : `${this.n} waiting`; },
    open() { wb.open('review'); },
  }));

  wb.data('appsWidget', () => ({
    get apps() { return wb.registry.list('app'); },
    launch(a) { if (a.embed === 'window') window.open(a.url, `wb-app-${a.id}`, 'noopener'); else wb.open('app', {app: a.id}, {title: a.title}); },
  }));

  wb.data('listView', () => ({
    type: null, schema: {}, rows: [], total: 0, q: '', sort: 'updated_at', desc: true, page: 0, size: 50, loading: true, error: '',
    init() {
      const panel = wb.panelOf(this.$el);
      this.type = wb.type(panel.params.type) || {id: panel.params.type, label: panel.params.type, schema: {}};
      this.schema = this.type.schema || {};
      this.$watch('q', () => { this.page = 0; this.load(); });
      this.load();
      this.off = wb.onChange((e) => e.kind === 'item' && e.type === this.type.id, () => this.load());
    },
    destroy() { this.off && this.off(); },
    // title, then up to three short fields, then when and by whom
    get columns() {
      const props = Object.entries(this.schema.properties || {})
        .filter(([, p]) => ['string', 'integer', 'number', 'boolean'].includes(p.type) && p.format !== 'markdown' && !/description|body/i.test(p.title || ''))
        .slice(0, 3).map(([name, p]) => ({name, label: p.title || name}));
      return [{name: 'title', label: 'Title'}, ...props, {name: 'updated_at', label: 'Updated'}, {name: 'updated_by', label: 'By'}];
    },
    async load() {
      this.loading = true; this.error = '';
      try {
        const r = await wb.api.get(this.type.id, {
          order: `${this.sort}.${this.desc ? 'desc' : 'asc'}.nullslast`, limit: this.size, offset: this.page * this.size,
          ...(this.q.trim() ? {or: `(title.ilike.*${this.q.trim()}*,slug.ilike.*${this.q.trim()}*)`} : {}),
        }, {count: true});
        this.rows = r.rows; this.total = r.total;
      } catch (e) { this.error = e.message; }
      this.loading = false;
    },
    sortBy(c) { if (this.sort === c.name) this.desc = !this.desc; else { this.sort = c.name; this.desc = c.name === 'updated_at'; } this.load(); },
    sortMark(c) { return this.sort === c.name ? (this.desc ? '↓' : '↑') : ''; },
    cell(r, c) { return c.name === 'updated_at' ? ago(r.updated_at) : show(r[c.name]); },
    open(r, e) { wb.open('item', {type: this.type.id, id: r.id}, {where: e && (e.ctrlKey || e.metaKey) ? 'right' : 'tab'}); },
    create() { wb.open('item', {type: this.type.id, id: 'new'}); },
    get canEdit() { return wb.canEdit(); },
    get summary() {
      if (this.loading) return 'Loading…';
      if (!this.total) return this.q ? 'Nothing matches.' : 'Nothing here yet.';
      const from = this.page * this.size + 1; const to = Math.min(this.total, from + this.rows.length - 1);
      return `${from}–${to} of ${this.total}`;
    },
    get hasPrev() { return this.page > 0; },
    get hasNext() { return (this.page + 1) * this.size < this.total; },
    prev() { if (this.hasPrev) { this.page -= 1; this.load(); } },
    next() { if (this.hasNext) { this.page += 1; this.load(); } },
  }));

  wb.data('itemView', () => ({
    type: null, id: null, item: null, values: {}, original: {}, fields: [], claims: {}, saving: false, error: '', loading: true, focused: null, stale: '',
    async init() {
      const panel = wb.panelOf(this.$el);
      this.panel = panel;
      this.type = wb.type(panel.params.type) || {id: panel.params.type, label: panel.params.type, schema: {}};
      this.id = panel.params.id;
      const props = (this.type.schema || {}).properties || {};
      this.fields = [
        {name: 'title', label: 'Title', kind: 'text', required: true, description: ''},
        {name: 'slug', label: 'Slug', kind: 'text', description: 'lowercase letters, digits, dots, dashes; unique'},
        ...Object.entries(props).filter(([n]) => !FRAME.includes(n)).map(([name, p]) => {
          const f = fieldFor(wb, {...p, name});
          return {name, label: p.title || name.replace(/_/g, ' '), kind: f ? f.kind || f.id : 'json', mount: f && f.mount, description: p.description || ''};
        }),
      ];
      await this.load();
      this.off = wb.onChange((e) => e.kind === 'item' && e.id === this.id, (evs) => {
        const others = evs.filter((e) => e.author !== (wb.user && wb.user.name));
        if (!others.length || this.saving) { this.loadClaims(); return; }
        if (this.dirty) { this.stale = `Changed by ${others[others.length - 1].author} while you were editing. Save to keep yours, or revert to see theirs.`; this.loadClaims(); return; }
        this.load();
      });
    },
    destroy() { this.off && this.off(); },
    async load() {
      this.loading = true; this.error = '';
      try {
        if (this.id !== 'new') {
          const rows = await wb.api.get(this.type.id, {id: `eq.${this.id}`});
          this.item = rows[0] || null;
          if (!this.item) { this.error = 'This item no longer exists, or you cannot see it.'; return; }
          this.panel.setTitle(this.item.title);
          await this.loadClaims();
        }
        const v = {};
        for (const f of this.fields) v[f.name] = this.toInput(f, this.item ? this.item[f.name] : null);
        this.values = v; this.original = {...v};
        this.select(null);
      } catch (e) { this.error = e.message; } finally { this.loading = false; }
    },
    async loadClaims() {
      const rows = await wb.api.get('claims', {subject_id: `eq.${this.id}`, status: 'in.(current,disputed)', select: 'field,author,value'}).catch(() => []);
      const by = {};
      for (const c of rows) (by[c.field] = by[c.field] || []).push(c);
      this.claims = by;
    },
    toInput(f, v) {
      if (v === null || v === undefined) return f.kind === 'boolean' ? false : '';
      if (f.kind === 'tags') return Array.isArray(v) ? v.join(', ') : String(v);
      if (f.kind === 'json') return JSON.stringify(v, null, 2);
      if (f.kind === 'datetime') return String(v).slice(0, 16);
      return v;
    },
    fromInput(f, v) {
      if (f.kind === 'boolean') return Boolean(v);
      if (v === '' || v === null) return null;
      if (f.kind === 'number') return Number(v);
      if (f.kind === 'tags') return String(v).split(',').map((s) => s.trim()).filter(Boolean);
      if (f.kind === 'json') return JSON.parse(v);
      if (f.kind === 'datetime') return new Date(v).toISOString();
      return v;
    },
    value(f) { return this.values[f.name]; },
    setValue(f, e) { const v = {...this.values}; v[f.name] = e.target.type === 'checkbox' ? e.target.checked : e.target.value; this.values = v; },
    is(f, k) { return f.kind === k; },
    custom(f) { return Boolean(f.mount); },
    mountField(el, f) { f.mount(el, {value: this.values[f.name], set: (v) => { const n = {...this.values}; n[f.name] = v; this.values = n; }, wb}); },
    changed(f) { return JSON.stringify(this.values[f.name]) !== JSON.stringify(this.original[f.name]); },
    get dirty() { return this.fields.some((f) => this.changed(f)); },
    get readOnly() { return !wb.canEdit(); },
    get isNew() { return this.id === 'new'; },
    sources(f) { return (this.claims[f.name] || []).length; },
    disagree(f) { const c = this.claims[f.name] || []; return new Set(c.map((x) => JSON.stringify(x.value))).size > 1; },
    sourceText(f) { const n = this.sources(f); return n === 0 ? '' : this.disagree(f) ? `${n} sources disagree` : n === 1 ? '1 source' : `${n} sources`; },
    select(f) {
      this.focused = f ? f.name : null;
      wb.select(this.isNew ? null : {type: this.type.id, id: this.id, field: this.focused, title: this.item && this.item.title});
    },
    isFocused(f) { return this.focused === f.name; },
    meta() { return this.item ? `Updated ${ago(this.item.updated_at)} by ${this.item.updated_by || 'unknown'}` : ''; },
    async save() {
      this.saving = true; this.error = '';
      try {
        const body = {};
        for (const f of this.fields) if (this.isNew ? this.values[f.name] !== '' : this.changed(f)) body[f.name] = this.fromInput(f, this.values[f.name]);
        if (this.isNew) {
          const row = await wb.api.post(this.type.id, body);
          wb.emit('saved', {type: this.type.id, id: row.id});
          this.panel.close();
          wb.open('item', {type: this.type.id, id: row.id});
          return;
        }
        this.item = await wb.api.patch(this.type.id, {id: `eq.${this.id}`}, body);
        this.panel.setTitle(this.item.title);
        const v = {};
        for (const f of this.fields) v[f.name] = this.toInput(f, this.item[f.name]);
        this.values = v; this.original = {...v}; this.stale = '';
        await this.loadClaims();
        wb.emit('saved', {type: this.type.id, id: this.id});
        wb.emit('claims-changed', {id: this.id});
        wb.notify('Saved');
      } catch (e) { this.error = e.message; } finally { this.saving = false; }
    },
    revert() { this.values = {...this.original}; if (this.stale) { this.stale = ''; this.load(); } },
  }));

  wb.data('provenance', () => ({
    rows: [], loading: false, seq: 0,
    init() {
      this.$watch('sel', () => this.load());
      this.off = wb.onChange((e) => e.kind === 'item' && this.sel && e.id === this.sel.id, () => this.load());
      this.load();
    },
    destroy() { this.off && this.off(); },
    get sel() { return wb.state.selection; },
    get heading() { const s = this.sel; return s && s.field ? `“${s.field}”` : 'Every field'; },
    async load() {
      const s = this.sel; if (!s || !s.id) { this.rows = []; return; }
      const seq = ++this.seq; this.loading = true;
      const q = {subject_id: `eq.${s.id}`, order: 'observed_at.desc', limit: 50,
                 select: 'id,field,value,author,status,observed_at,quote,source_id,run_id'};
      if (s.field) q.field = `eq.${s.field}`;
      const rows = await wb.api.get('claims', q).catch(() => []);
      if (seq === this.seq) { this.rows = rows; this.loading = false; }
    },
    value(c) { return show(c.value); },
    ago(c) { return ago(c.observed_at); },
    exact(c) { return when(c.observed_at); },
    statusClass(c) { return 'wb-claim wb-claim-' + c.status; },
    origin(c) { return c.run_id ? 'an extractor run' : c.source_id ? 'a source' : 'typed in'; },
    get empty() { return !this.loading && this.rows.length === 0; },
  }));

  wb.data('itemInfo', () => ({
    item: null,
    init() { this.$watch('sel', () => this.load()); this.off = wb.onChange((e) => e.kind === 'item' && this.sel && e.id === this.sel.id, () => this.load()); this.load(); },
    destroy() { this.off && this.off(); },
    get sel() { return wb.state.selection; },
    async load() {
      const s = this.sel; if (!s || !s.id) { this.item = null; return; }
      const rows = await wb.api.get(s.type, {id: `eq.${s.id}`, select: 'id,slug,created_at,created_by,updated_at,updated_by'}).catch(() => []);
      this.item = rows[0] || null;
    },
    created() { return this.item ? `${when(this.item.created_at)} by ${this.item.created_by || '?'}` : ''; },
    updated() { return this.item ? `${when(this.item.updated_at)} by ${this.item.updated_by || '?'}` : ''; },
    get link() { const s = this.sel; return s ? `${location.origin}/#view=item&type=${s.type}&id=${s.id}` : ''; },
    copy() { navigator.clipboard?.writeText(this.link).then(() => wb.notify('Link copied')); },
  }));

  wb.data('claimsView', () => ({
    rows: [], author: '', status: 'current', type: '', loading: true,
    init() {
      this.load(); this.$watch('author', () => this.load()); this.$watch('status', () => this.load()); this.$watch('type', () => this.load());
      this.off = wb.onChange((e) => e.kind === 'item', () => this.load(), 800);
    },
    destroy() { this.off && this.off(); },
    get types() { return wb.state.types; },
    async load() {
      this.loading = true;
      const q = {order: 'observed_at.desc', limit: 200, select: 'id,subject_type,subject_id,field,value,author,status,observed_at'};
      if (this.author.trim()) q.author = `ilike.*${this.author.trim()}*`;
      if (this.status) q.status = `eq.${this.status}`;
      if (this.type) q.subject_type = `eq.${this.type}`;
      this.rows = await wb.api.get('claims', q).catch(() => []);
      this.loading = false;
    },
    label(c) { return wb.type(c.subject_type)?.label || c.subject_type; },
    value(c) { return show(c.value); },
    ago(c) { return ago(c.observed_at); },
    open(c) { wb.open('item', {type: c.subject_type, id: c.subject_id}); wb.select({type: c.subject_type, id: c.subject_id, field: c.field}); },
  }));

  wb.data('reviewView', () => ({
    rows: [], status: 'open', notes: {}, loading: true,
    init() { this.load(); this.$watch('status', () => this.load()); this.off = wb.onChange((e) => e.kind === 'decision', () => this.load()); },
    destroy() { this.off && this.off(); },
    async load() {
      this.loading = true;
      this.rows = await wb.api.get('decisions', {order: 'created_at.desc', limit: 200, ...(this.status ? {status: `eq.${this.status}`} : {})}).catch(() => []);
      this.loading = false;
    },
    subject(d) { return show(d.subject && (d.subject.text || d.subject.title || d.subject)); },
    ago(d) { return ago(d.created_at); },
    decidedText(d) { return d.status === 'open' ? '' : `${d.status} by ${d.decided_by} ${ago(d.decided_at)}${d.note ? ': ' + d.note : ''}`; },
    isOpen(d) { return d.status === 'open'; },
    setNote(d, e) { const n = {...this.notes}; n[d.id] = e.target.value; this.notes = n; },
    async decide(d, approve) {
      try {
        await wb.api.rpc('decide', {id: d.id, approve, note: this.notes[d.id] || null});
        wb.notify(approve ? 'Approved' : 'Declined');
      } catch (e) { wb.notify(e.message, 'error'); }
    },
    get canEdit() { return wb.canEdit(); },
    get empty() { return !this.loading && this.rows.length === 0; },
  }));

  wb.data('typesView', () => ({
    get types() { return wb.state.types; },
    props(t) { return Object.entries((t.schema || {}).properties || {}).map(([name, p]) => ({name, type: p.format ? `${p.type} (${p.format})` : p.type || 'any', description: p.description || ''})); },
    open(t) { wb.open('list', {type: t.id}); },
  }));

  wb.data('extractorsView', () => ({
    extractors: [], runs: [], error: '', busy: {},
    init() { this.load(); this.off = wb.onChange((e) => e.kind === 'run', () => this.loadRuns(), 200); },
    destroy() { this.off && this.off(); },
    async load() {
      try { this.extractors = await wb.api.server('GET', 'extractors'); } catch (e) { this.error = `The Workbench server did not answer: ${e.message}`; }
      this.loadRuns();
    },
    async loadRuns() { this.runs = await wb.api.get('runs', {order: 'started_at.desc', limit: 30}).catch(() => []); },
    get canRun() { return wb.canEdit(); },
    isBusy(x) { return Boolean(this.busy[x.key]); },
    async run(x) {
      const b = {...this.busy}; b[x.key] = true; this.busy = b;
      try { await wb.api.server('POST', 'extract', {extractor: x.key, inputs: {}}); wb.notify(`Queued ${x.key}`); }
      catch (e) { wb.notify(e.message, 'error'); }
      setTimeout(() => { const n = {...this.busy}; delete n[x.key]; this.busy = n; }, 1500);
    },
    state(r) { return !r.ended_at ? 'running' : r.outcome && r.outcome.ok ? 'done' : 'failed'; },
    stateClass(r) { const s = this.state(r); return 'wb-pill ' + (s === 'done' ? 'is-current' : s === 'failed' ? 'is-retracted' : 'is-disputed'); },
    summary(r) {
      const o = r.outcome || {};
      if (o.ok === false) return o.error || 'failed';
      const parts = [];
      for (const k of ['items', 'sources', 'relations', 'decisions', 'withdrawn']) if (o[k]) parts.push(`${o[k]} ${k}`);
      return [parts.join(', '), ...(o.log || [])].filter(Boolean).join(' · ') || 'nothing new';
    },
    ago(r) { return ago(r.started_at); },
    by(r) { return (r.inputs && r.inputs.requested_by) || 'command line'; },
  }));
}
