// The papers package's plugin, browser side: one view, the papers (docs/archive/tasks/paper-catalog.md). A table with filters
// for the heading a list put the paper under, the listing, how many listings name it, the date, a repository and the
// testable flag, and for what a model read from the abstract (kind, slot, trial); a need described in words is searched with
// recall limited to papers (the lookup), the filters applied to what it ranks; a row can be queued for a trial with a reason. A row opens to the listings that name it (each with its heading and a link to the line), and "Open"
// goes to the item, where every value has its claims and sources beside it.
export default function papers(wb) {
  wb.view({id: 'papers-list', title: () => 'Papers', template: 'papers-tpl-list', key: () => 'papers-list'});
  wb.menu({id: 'papers-list', section: 'Workspace', title: 'Papers', icon: 'doc', open: ['papers-list'], order: 3});
  wb.command({id: 'papers-list', title: 'Open the paper catalog', run: () => wb.open('papers-list')});

  wb.data('papersList', () => ({
    rows: [], listings: {}, loading: true, shown_n: 100, opened: {},
    sort: 'listings', need: '', ranked: null, searching: false, searchError: '', queueing: {},
    f: {text: '', heading: '', listing: '', min: '1', cites: '', from: '', repo: 'any', testable: 'any', kind: '', slot: '', trial: ''},
    kinds: ['memory', 'planning', 'tool-use', 'reflection', 'skill-library', 'routing', 'multi-agent', 'self-improvement', 'evaluation', 'world-model', 'prompt-optimization', 'benchmark', 'survey', 'other'],
    slots: ['handler', 'route', 'notes', 'sensor', 'learner', 'outcome', 'none'],
    trials: ['queued', 'running', 'replicated', 'not replicated', 'dropped'],
    init() {
      this.load();
      this.off = wb.onChange((e) => e.kind === 'item' && ['paper', 'listing'].includes(e.type), () => this.load(), 3000);
    },
    destroy() { this.off && this.off(); },
    async load() {
      const [papers, listings] = await Promise.all([
        wb.api.get('paper', {select: 'id,slug,title,arxiv_id,published,citations,venue,listing_count,listed_in,repositories,testable,testable_why,component_kind,slot,does,result,needs,record_by,trial,trial_why',
                             order: 'listing_count.desc.nullslast,published.desc.nullslast', limit: 50000}).catch(() => []),
        wb.api.get('listing', {select: 'slug,title,url,kind,licence,machine_built,entries', order: 'slug'}).catch(() => []),
      ]);
      this.listings = Object.fromEntries(listings.map((l) => [l.slug, l]));
      this.listingList = listings;
      this.rows = papers.map((p) => ({...p, headings: [...new Set((p.listed_in || []).map((e) => e.heading).filter(Boolean))],
                                      haystack: `${p.title} ${p.arxiv_id} ${(p.listed_in || []).map((e) => e.heading).join(' ')}`.toLowerCase()}));
      this.loading = false;
    },
    listingList: [],
    get shown() {
      const f = this.f, t = f.text.trim().toLowerCase(), h = f.heading.trim().toLowerCase(), min = Number(f.min) || 0;
      return this.rows.filter((p) => (!t || p.haystack.includes(t))
        && (!h || p.headings.some((x) => x.toLowerCase().includes(h)))
        && (!f.listing || (p.listed_in || []).some((e) => e.listing === f.listing))
        && (p.listing_count || 0) >= min
        && (!f.cites || (p.citations || 0) >= Number(f.cites))
        && (!f.from || (p.published || '') >= f.from)
        && (f.repo === 'any' || ((p.repositories || []).length > 0) === (f.repo === 'yes'))
        && (!f.kind || p.component_kind === f.kind) && (!f.slot || p.slot === f.slot)
        && (!f.trial || (f.trial === 'none' ? !p.trial : p.trial === f.trial))
        && (!this.ranked || this.ranked.has(p.id))
        && (f.testable === 'any' || (f.testable === 'unchecked' ? p.testable === null || p.testable === undefined : p.testable === (f.testable === 'yes'))));
    },
    get sorted() {
      const by = {listings: (a, b) => (b.listing_count || 0) - (a.listing_count || 0),
                  citations: (a, b) => (b.citations ?? -1) - (a.citations ?? -1),
                  published: (a, b) => (b.published || '').localeCompare(a.published || '')}[this.sort];
      if (this.ranked) return [...this.shown].sort((a, b) => this.ranked.get(a.id) - this.ranked.get(b.id));   // the lookup's order
      return [...this.shown].sort(by);
    },
    get visible() { return this.sorted.slice(0, this.shown_n); },
    get summary() { return this.loading ? 'Loading…' : `${this.shown.length} of ${this.rows.length} papers · ${this.listingList.length} listings`; },
    more() { this.shown_n += 200; },
    reset() {
      this.f = {text: '', heading: '', listing: '', min: '1', cites: '', from: '', repo: 'any', testable: 'any', kind: '', slot: '', trial: ''};
      this.need = ''; this.ranked = null; this.searchError = ''; this.shown_n = 100;
    },
    // the lookup: recall limited to papers, as the signed-in person; its order replaces the sort, and the filters above still apply
    async search() {
      const q = this.need.trim();
      if (!q) { this.ranked = null; return; }
      this.searching = true; this.searchError = '';
      try {
        const hits = await wb.api.server('POST', 'recall', {q, limit: 300, types: ['paper']});
        this.ranked = new Map(hits.map((h, i) => [h.id, i]));
        this.shown_n = 100;
      } catch (e) { this.searchError = e.message || 'the search failed'; this.ranked = null; }
      this.searching = false;
    },
    get findLabel() { return this.searching ? 'Searching…' : 'Find'; },
    get rankedNote() { return this.ranked ? `ranked by meaning, words and the graph: ${this.ranked.size} papers; the filters below still apply` : ''; },
    busy(p) { return Boolean(this.queueing[p.id]); },
    drop(p) { return this.setTrial(p, 'dropped'); },
    clearSearch() { this.need = ''; this.ranked = null; this.searchError = ''; },
    // queue a paper for a trial: trial = queued and why, as a claim of the person who sets them
    async queue(p) {
      const why = (window.prompt('Why try this paper? (shown beside it, kept as a claim of yours)', p.trial_why || '') || '').trim();
      if (!why) return;
      this.queueing = {...this.queueing, [p.id]: true};
      try {
        const row = await wb.api.patch('paper', {id: `eq.${p.id}`}, {trial: 'queued', trial_why: why});
        Object.assign(p, {trial: row.trial, trial_why: row.trial_why});
        this.rows = [...this.rows];
      } catch (e) { window.alert(e.message || 'could not queue it'); }
      this.queueing = {...this.queueing, [p.id]: false};
    },
    async setTrial(p, value) {
      const why = (window.prompt(`Why ${value}?`, p.trial_why || '') || '').trim();
      if (!why) return;
      const row = await wb.api.patch('paper', {id: `eq.${p.id}`}, {trial: value, trial_why: why}).catch((e) => { window.alert(e.message); return null; });
      if (row) { Object.assign(p, {trial: row.trial, trial_why: row.trial_why}); this.rows = [...this.rows]; }
    },
    toggle(p) { this.opened = {...this.opened, [p.id]: !this.opened[p.id]}; },
    isOpen(p) { return Boolean(this.opened[p.id]); },
    open(p) { wb.open('item', {type: 'paper', id: p.id}); },
    cites(p) { return p.citations === null || p.citations === undefined ? '—' : String(p.citations); },
    day(p) { return p.published || '—'; },
    flag(p) { return p.testable === true ? 'testable' : p.testable === false ? 'no' : 'not checked'; },
    flagClass(p) { return 'wb-pill ' + (p.testable === true ? 'is-current' : p.testable === false ? 'is-retracted' : ''); },
    listingTitle(slug) { return (this.listings[slug] || {}).title || slug; },
    arxivUrl(p) { return `https://arxiv.org/abs/${p.arxiv_id}`; },
    repoUrl(r) { return `https://github.com/${r}`; },
  }));
}
