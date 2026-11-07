// The console's page logic (S-22). A file of its own: the CSP allows scripts from this origin only.

// The map's graph lives outside Alpine's reactive state (Cytoscape keeps its own).
let cy = null;
const SYSTEMS = ['interface', 'mind', 'organism', 'engine', 'storage', 'outside'];
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

document.addEventListener('alpine:init', () => {
  Alpine.data('substrateConsole', () => ({
    signedIn: null, name: 'owner', password: '', signinError: '',
    s: null, loading: false, error: '', lastOk: 0, now: Date.now(),
    draft: '', busy: {}, flash: '', open: {},
    view: 'overview', m: null, mode: 'difference', mapError: '', picked: null,

    async init() {
      this.route();
      window.addEventListener('hashchange', () => this.route());
      setInterval(() => { if (this.signedIn && this.view === 'map' && !document.hidden) this.loadMap(); }, 30000);
      await this.refresh();
      setInterval(() => { this.now = Date.now(); }, 1000);
      setInterval(() => { if (this.signedIn && !document.hidden) this.refresh(); }, 10000);
      document.addEventListener('visibilitychange', () => { if (!document.hidden && this.signedIn) this.refresh(); });
    },
    async call(path, body) {
      const r = await fetch(path, body === undefined ? { credentials: 'same-origin' } : {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      let data = {}; try { data = await r.json(); } catch (e) {}
      return { status: r.status, data };
    },
    async refresh() {
      if (this.loading) return;
      this.loading = true;
      try {
        const { status, data } = await this.call('api/state');
        if (status === 401) { this.signedIn = false; this.s = null; return; }
        if (status !== 200) { this.error = data.error || ('the console answered ' + status); return; }
        this.s = data; this.signedIn = true; this.error = ''; this.lastOk = Date.now();
        if (this.view === 'map' && !this.m) this.loadMap();
      } catch (e) {
        this.error = 'the console did not answer; the stack may be down (scripts/check.sh)';
      } finally { this.loading = false; }
    },
    async signIn() {
      this.signinError = '';
      const { status, data } = await this.call('api/login', { name: this.name, password: this.password });
      if (status !== 200) { this.signinError = data.error || 'sign-in failed'; return; }
      this.password = ''; await this.refresh();
    },
    async signOut() { await this.call('api/logout', {}); this.signedIn = false; this.s = null; },
    async decide(item, approve) {
      this.busy[item.id] = true;
      const { status, data } = await this.call('api/review', { id: item.id, approve, note: approve ? 'approved in the console' : 'declined in the console' });
      this.busy[item.id] = false;
      this.flash = status === 200 ? (approve ? 'Approved: ' : 'Declined: ') + item.title : (data.error || 'kernel refused the review');
      await this.refresh();
    },
    async propose() {
      const text = this.draft.trim(); if (!text) return;
      const { status, data } = await this.call('api/goal', { text });
      this.flash = status === 200 ? 'Goal sent to the owner queue' : (data.error || 'the bus refused the goal');
      if (status === 200) this.draft = '';
      await this.refresh();
    },

    route() {
      this.view = location.hash === '#map' ? 'map' : 'overview';
      if (this.view === 'map') this.$nextTick(() => this.loadMap());
    },
    async loadMap() {
      if (!this.signedIn) return;
      const { status, data } = await this.call('api/map');
      if (status === 401) { this.signedIn = false; return; }
      if (status !== 200) { this.mapError = data.error || ('the map answered ' + status); return; }
      this.m = data; this.mapError = '';
      this.$nextTick(() => this.draw());
    },
    setMode(mode) { this.mode = mode; this.picked = null; this.draw(); },
    get gapCount() { return this.m ? this.m.edges.filter(e => e.standing === 'unseen' || e.standing === 'undeclared').length : 0; },

    // One layout for every mode: a column per catalog system (and one for what is outside), so the intended and
    // the observed graphs can be compared by position.
    elements() {
      const m = this.m, mode = this.mode, cols = {}, els = [];
      const nodes = m.nodes.map(n => ({ ...n }));
      for (const x of m.external) nodes.push({ id: x, system: 'outside', external: true });
      for (const n of nodes) (cols[SYSTEMS.includes(n.system) ? n.system : 'engine'] ||= []).push(n);
      SYSTEMS.forEach((sys, c) => {
        const list = (cols[sys] || []).sort((a, b) => a.id.localeCompare(b.id));
        if (!list.length) return;
        els.push({ group: 'nodes', data: { id: 'sys:' + sys, label: sys.toUpperCase(), w: 120 }, classes: 'sys',
                   position: { x: c * 210, y: 0 }, selectable: false });
        list.forEach((n, r) => {
          const up = m.up[n.id];
          let cls = n.external ? 'ext' : '';
          if (mode === 'intended') cls = n.external ? 'hidden' : n.state;
          else if (!n.external) cls = up ? (up.ok ? 'up' : 'down') : 'quiet';
          els.push({ group: 'nodes', data: { id: n.id, label: n.id, w: Math.max(70, n.id.length * 7 + 22), n },
                     classes: cls, position: { x: c * 210, y: 52 + r * 50 } });
        });
      });
      for (const e of m.edges) {
        let show = false, cls = e.standing;
        if (mode === 'intended') { show = e.standing !== 'undeclared'; cls = 'declared'; }
        else if (mode === 'observed') { show = e.standing === 'confirmed' || e.standing === 'undeclared'; cls = 'observed'; }
        else show = e.standing !== 'unobservable';
        if (show) els.push({ group: 'edges', data: { id: e.source + '>' + e.target, source: e.source, target: e.target,
                                                     calls: e.calls || 0, e }, classes: cls });
      }
      return els.filter(x => x.classes !== 'hidden');
    },
    draw() {
      if (!this.m || !this.$refs.graph || typeof cytoscape === 'undefined') return;
      const ink = css('--ink'), muted = css('--muted'), line = css('--line'), panel = css('--panel');
      const style = [
        { selector: 'node', style: { label: 'data(label)', 'font-size': 11, color: ink, 'text-valign': 'center',
            'text-halign': 'center', width: 'data(w)', height: 26, shape: 'round-rectangle', 'background-color': panel,
            'border-width': 1.5, 'border-color': line, 'font-family': 'system-ui, sans-serif' } },
        { selector: 'node.sys', style: { 'background-opacity': 0, 'border-width': 0, color: muted, 'font-size': 10,
            'font-weight': 600, events: 'no' } },
        { selector: 'node.built', style: { 'background-color': css('--accent'), 'border-color': css('--accent'), color: panel } },
        { selector: 'node.building', style: { 'background-color': css('--warn-soft'), 'border-color': css('--warn'), 'border-width': 2 } },
        { selector: 'node.planned', style: { 'border-style': 'dashed', 'border-color': muted, color: muted } },
        { selector: 'node.up', style: { 'background-color': css('--ok-soft'), 'border-color': css('--ok'), 'border-width': 2 } },
        { selector: 'node.down', style: { 'background-color': css('--bad-soft'), 'border-color': css('--bad'), 'border-width': 2 } },
        { selector: 'node.quiet', style: { color: muted, opacity: 0.55 } },
        { selector: 'node.ext', style: { 'border-style': 'dotted', 'border-color': muted, 'border-width': 2 } },
        { selector: 'edge', style: { width: 1.4, 'line-color': line, 'target-arrow-color': line, 'target-arrow-shape': 'triangle',
            'arrow-scale': 0.8, 'curve-style': 'bezier' } },
        { selector: 'edge.declared', style: { 'line-color': muted, 'target-arrow-color': muted, opacity: 0.5 } },
        { selector: 'edge.observed, edge.confirmed', style: { 'line-color': css('--ok'), 'target-arrow-color': css('--ok'),
            width: 'mapData(calls, 0, 500, 1.5, 5)' } },
        { selector: 'edge.unseen', style: { 'line-style': 'dashed', 'line-color': muted, 'target-arrow-color': muted } },
        { selector: 'edge.undeclared', style: { 'line-color': css('--bad'), 'target-arrow-color': css('--bad'), width: 3 } },
        { selector: ':selected', style: { 'overlay-color': css('--accent'), 'overlay-opacity': 0.15 } },
      ];
      if (cy) cy.destroy();
      cy = cytoscape({ container: this.$refs.graph, elements: this.elements(), style, layout: { name: 'preset', padding: 24 },
                       wheelSensitivity: 0.3, boxSelectionEnabled: false });
      cy.on('tap', 'node', (ev) => this.pickNode(ev.target.data('n')));
      cy.on('tap', 'edge', (ev) => this.pickEdge(ev.target.data('e')));
      cy.on('tap', (ev) => { if (ev.target === cy) this.picked = null; });
    },
    pickNode(n) {
      if (!n) return;
      const up = this.m.up[n.id];
      const rows = n.external ? [['seen', 'called from inside, not in the catalog']] : [
        ['system', n.system], ['fill', n.fill || '–'], ['intended', n.state + (n.step != null ? ' (step ' + n.step + ': ' + n.step_status + ')' : '')],
        ['observed', up ? (up.ok ? 'running' : 'not answering') + ' · ' + up.how : (n.runtime ? 'not seen' : 'not a running part')],
        ['about', n.description || '–']];
      this.picked = { title: n.id, rows };
      this.$nextTick(() => cy && cy.resize());
    },
    pickEdge(e) {
      if (!e) return;
      const words = { confirmed: 'declared and seen', unseen: 'declared, not seen in the last hour',
                      undeclared: 'seen, not declared in the catalog', unobservable: 'declared; not observable yet' };
      const rows = [['standing', words[e.standing] || e.standing]];
      if (e.via) rows.push(['declared', e.via.join(', ')]);
      if (e.calls != null) rows.push(['calls', e.calls + ' in the last hour' + (e.failed ? ', ' + e.failed + ' failed' : '')]);
      if (e.evidence) rows.push(['evidence', e.evidence]);
      this.picked = { title: e.source + ' → ' + e.target, rows };
      this.$nextTick(() => cy && cy.resize());
    },

    get okCount() { return this.s ? this.s.services.filter(x => x.ok).length : 0; },
    get reviewCount() { return this.s && this.s.review.ok ? this.s.review.items.length : null; },
    get ago() { if (!this.lastOk) return ''; const d = Math.round((this.now - this.lastOk) / 1000); return d < 2 ? 'just now' : d + 's ago'; },
    money(v) { return '$' + (Number(v) || 0).toFixed(2); },
    tokens(v) { v = Number(v) || 0; return v >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(1) + 'k' : String(Math.round(v)); },
    when(t) { if (!t) return ''; const d = new Date(t); return isNaN(d) ? t : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); },
    stepClass(st) { return st.status === 'done' ? 'done' : st.status === 'doing' ? 'doing' : st.needs_owner ? 'blocked' : ''; },
    providerPct(p) { const max = Math.max(...this.s.spend.providers.map(x => x.usd), 0) || 1; return p.usd / max * 100; },
    spark(fill) {
      const d = (this.s && this.s.spend.days) || []; if (d.length < 2) return '';
      const w = 150, h = 40, pad = 3, max = Math.max(...d) || 1;
      const pts = d.map((v, i) => [pad + i * (w - 2 * pad) / (d.length - 1), h - pad - v / max * (h - 2 * pad)]);
      const line = pts.map(p => p.map(n => n.toFixed(1)).join(',')).join(' ');
      return fill ? `${pad},${h - pad} ${line} ${w - pad},${h - pad}` : line;
    },
    get lastPoint() {
      const d = (this.s && this.s.spend.days) || []; if (!d.length) return { x: -10, y: -10 };
      const max = Math.max(...d) || 1; return { x: 147, y: 40 - 3 - d[d.length - 1] / max * 34 };
    },
  }));
});
