// The papers package's plugin, browser side: one view, the papers (docs/tasks/paper-catalog.md). A table with filters
// for the heading a list put the paper under, the listing, how many listings name it, the date, a repository and the
// testable flag; a row opens to the listings that name it (each with its heading and a link to the line), and "Open"
// goes to the item, where every value has its claims and sources beside it.
export default function papers(wb) {
  wb.view({id: 'papers-list', title: () => 'Papers', template: 'papers-tpl-list', key: () => 'papers-list'});
  wb.menu({id: 'papers-list', section: 'Workspace', title: 'Papers', icon: 'doc', open: ['papers-list'], order: 3});
  wb.command({id: 'papers-list', title: 'Open the paper catalog', run: () => wb.open('papers-list')});

  wb.data('papersList', () => ({
    rows: [], listings: {}, loading: true, shown_n: 100, opened: {},
    sort: 'listings',
    f: {text: '', heading: '', listing: '', min: '1', cites: '', from: '', repo: 'any', testable: 'any'},
    init() {
      this.load();
      this.off = wb.onChange((e) => e.kind === 'item' && ['paper', 'listing'].includes(e.type), () => this.load(), 3000);
    },
    destroy() { this.off && this.off(); },
    async load() {
      const [papers, listings] = await Promise.all([
        wb.api.get('paper', {select: 'id,slug,title,arxiv_id,published,citations,venue,listing_count,listed_in,repositories,testable,testable_why',
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
        && (f.testable === 'any' || (f.testable === 'unchecked' ? p.testable === null || p.testable === undefined : p.testable === (f.testable === 'yes'))));
    },
    get sorted() {
      const by = {listings: (a, b) => (b.listing_count || 0) - (a.listing_count || 0),
                  citations: (a, b) => (b.citations ?? -1) - (a.citations ?? -1),
                  published: (a, b) => (b.published || '').localeCompare(a.published || '')}[this.sort];
      return [...this.shown].sort(by);
    },
    get visible() { return this.sorted.slice(0, this.shown_n); },
    get summary() { return this.loading ? 'Loading…' : `${this.shown.length} of ${this.rows.length} papers · ${this.listingList.length} listings`; },
    more() { this.shown_n += 200; },
    reset() { this.f = {text: '', heading: '', listing: '', min: '1', cites: '', from: '', repo: 'any', testable: 'any'}; this.shown_n = 100; },
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
