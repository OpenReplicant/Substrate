// The console's page logic (S-22). A file of its own: the CSP allows scripts from this origin only.
document.addEventListener('alpine:init', () => {
  Alpine.data('substrateConsole', () => ({
    signedIn: null, name: 'owner', password: '', signinError: '',
    s: null, loading: false, error: '', lastOk: 0, now: Date.now(),
    draft: '', busy: {}, flash: '', open: {},

    async init() {
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
