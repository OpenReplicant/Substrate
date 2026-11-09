// Substrate's plugin, browser side (workbench/README.md, "Client plugins"). It adds:
//   - a dashboard widget: the system's components by lifecycle, built with mount() rather than an Alpine template,
//     to show the framework-free half of the contract.
//   - the Map: what the catalog declares against what the repository has (skills and hooks), the gaps between them
//     in the review lane, and the extractors that read both. An Alpine template (web/views.html).
export default function substrate(wb) {
  wb.view({id: 'substrate-map', title: () => 'Map', template: 'substrate-tpl-map', key: () => 'substrate-map'});
  wb.menu({id: 'substrate-map', section: 'Workspace', title: 'Map', icon: 'schema', open: ['substrate-map'], order: 2});
  wb.command({id: 'substrate-map', title: 'Open the map (declared against observed)', run: () => wb.open('substrate-map')});

  wb.data('substrateMap', () => ({
    rows: [], gaps: 0, loading: true, filter: 'all',
    init() {
      this.load();
      this.off = wb.onChange((e) => (e.kind === 'item' && ['component', 'skill', 'hook'].includes(e.type)) || e.kind === 'decision', () => this.load(), 500);
    },
    destroy() { this.off && this.off(); },
    async load() {
      const [declared, skills, hooks, gaps] = await Promise.all([
        wb.api.get('component', {kind: 'eq.AiResource', select: 'id,slug,title,type,lifecycle,description'}).catch(() => []),
        wb.api.get('skill', {select: 'id,slug,path,description'}).catch(() => []),
        wb.api.get('hook', {select: 'id,slug,path,event,matcher'}).catch(() => []),
        wb.api.get('decisions', {status: 'eq.open', raised_by: 'eq.substrate:drift', select: 'id,key,subject'}).catch(() => []),
      ]);
      const open = new Map(gaps.map((g) => [g.key, g]));
      const by = new Map();
      for (const d of declared) by.set(`${d.type}:${d.slug}`, {key: `${d.type}:${d.slug}`, type: d.type, slug: d.slug, declared: d, observed: null});
      for (const [type, list] of [['skill', skills], ['hook', hooks]]) {
        for (const o of list) {
          const k = `${type}:${o.slug}`;
          const row = by.get(k) || {key: k, type, slug: o.slug, declared: null, observed: null};
          row.observed = {...o, type};
          by.set(k, row);
        }
      }
      this.rows = [...by.values()].map((r) => { const g = open.get(`undeclared:${r.key}`) || open.get(`unobserved:${r.key}`); return {...r, gap: Boolean(g), decision: g || null}; })
        .sort((a, b) => (b.gap - a.gap) || a.type.localeCompare(b.type) || a.slug.localeCompare(b.slug));
      this.gaps = this.rows.filter((r) => r.gap).length;
      this.loading = false;
    },
    get shown() { return this.filter === 'gaps' ? this.rows.filter((r) => r.gap) : this.rows; },
    state(r) { return r.declared && r.observed ? 'matches' : r.declared ? 'declared, not found' : 'found, not declared'; },
    stateClass(r) { return 'wb-pill ' + (r.declared && r.observed ? 'is-current' : 'is-disputed'); },
    where(r) { return r.observed ? r.observed.path : '—'; },
    mark(x) { return x ? '✓' : '—'; },
    openDeclared(r) { if (r.declared) wb.open('item', {type: 'component', id: r.declared.id}); },
    openObserved(r) { if (r.observed) wb.open('item', {type: r.type, id: r.observed.id}); },
    review() { wb.open('review'); },
    get canDecide() { return wb.canEdit(); },
    // S-51: approving a gap changes the map; declining it changes the repository
    async decide(r, approve) {
      if (!r.decision) return;
      try {
        await wb.api.rpc('decide', {id: r.decision.id, approve,
          note: approve ? 'change the map (decided on the Map)' : 'change the repository (decided on the Map)'});
        wb.notify(approve ? `Decided: change the map for ${r.slug}` : `Decided: change the repository for ${r.slug}`);
      } catch (e) { wb.notify(e.message, 'error'); }
    },
    extractors() { wb.open('extractors'); },
    get summary() { return this.loading ? 'Loading…' : `${this.rows.length} parts · ${this.gaps} waiting for a decision`; },
  }));


  wb.widget({
    id: 'substrate-lifecycle', title: 'Components by lifecycle', size: 's', order: 10,
    when: (w) => Boolean(w.type('component')),
    mount(el, w) {
      const list = document.createElement('ul');
      list.className = 'wb-stat-list';
      el.append(list);
      let stale = false;
      w.api.get('component', {select: 'lifecycle'}).then((rows) => {
        if (stale) return;
        const counts = {};
        for (const r of rows) counts[r.lifecycle || 'unset'] = (counts[r.lifecycle || 'unset'] || 0) + 1;
        const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
        if (!entries.length) list.innerHTML = '<li class="wb-faint">No components yet. Step W3 reads them from catalog-info.yaml.</li>';
        for (const [lc, n] of entries) {
          const li = document.createElement('li');
          const name = Object.assign(document.createElement('span'), {textContent: lc});
          const num = Object.assign(document.createElement('span'), {className: 'wb-stat', textContent: String(n)});
          li.append(name, num);
          list.append(li);
        }
      }).catch((e) => { list.textContent = e.message; });
      return () => { stale = true; };
    },
  });
}
