// The UI (S-140): search the store, read an entity's page, and see a map as a diagram (Cytoscape.js with the
// dagre layered layout). Routes live in the hash: #/ (wholes), #/map/Q10, #/e/Q10. No inline script or style, so
// the page runs under script-src 'self'; style-src 'self'. Everything shown is set with textContent, never HTML.
"use strict";

const $ = id => document.getElementById(id);
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const KINDS = ["whole", "part", "role", "interface", "candidate"];
let cy = null, current = null, wholes = [];

async function get(path) {
  const r = await fetch(path);
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || r.statusText);
  return body;
}

function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "text") e.textContent = v; else if (k === "class") e.className = v; else e.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) e.append(k);
  return e;
}

// ---------- the list on the left: wholes, or search results ----------

function list(title, items, on) {
  const nav = $("list");
  nav.replaceChildren(el("h2", {text: title}));
  if (!items.length) nav.append(el("div", {class: "empty", text: "Nothing found."}));
  for (const it of items) {
    const a = el("a", {href: it.href, class: it.id === on ? "on" : ""}, it.label, it.sub ? el("small", {text: it.sub}) : null);
    nav.append(a);
  }
}

function showWholes(on) {
  list("Maps", wholes.map(w => ({id: w.id, href: `#/map/${w.id}`, label: w.label, sub: `${w.parts} part${w.parts === 1 ? "" : "s"} · ${w.id}`})), on);
}

let searchTimer = null;
$("q").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const q = $("q").value.trim();
    if (!q) return showWholes(current);
    const hits = await get(`/api/search?q=${encodeURIComponent(q)}`);
    list(`Results for “${q}”`, hits.map(h => ({id: h.id, href: `#/e/${h.id}`, label: h.label, sub: `${h.id}${h.description ? " · " + h.description : ""}`})), current);
  }, 180);
});

// ---------- a page: the store's markdown, rendered safely ----------

function inline(text) {
  // **bold**, `code`, and (Q12)/(P3) ids as links; everything else as text
  const out = document.createDocumentFragment();
  const re = /\*\*([^*]+)\*\*|`([^`]+)`|\(([QP][1-9][0-9]*)\)|(flagged: [^)\]]+)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.append(text.slice(last, m.index));
    if (m[1]) out.append(el("strong", {text: m[1]}));
    else if (m[2]) out.append(el("code", {text: m[2]}));
    else if (m[3]) out.append("(", el("a", {href: `#/e/${m[3]}`, text: m[3]}), ")");
    else out.append(el("span", {class: "flag", text: m[4]}));
    last = re.lastIndex;
  }
  if (last < text.length) out.append(text.slice(last));
  return out;
}

function markdown(md) {
  const root = el("div", {class: "md"});
  let ul = null, sub = null, ol = null;
  for (const line of md.split("\n")) {
    const h = /^(#{1,3}) (.*)$/.exec(line), li = /^- (.*)$/.exec(line), sli = /^ {2,}- (.*)$/.exec(line), oli = /^(\d+)\. (.*)$/.exec(line);
    if (h) { ul = sub = ol = null; root.append(el(`h${h[1].length}`, {}, inline(h[2]))); }
    else if (li) { ol = null; if (!ul) root.append(ul = el("ul")); const item = el("li", {}, inline(li[1])); ul.append(item); sub = null; ul.lastItem = item; }
    else if (sli && ul) { if (!sub) ul.lastItem.append(sub = el("ul")); sub.append(el("li", {}, inline(sli[1]))); }
    else if (oli) { ul = sub = null; if (!ol) root.append(ol = el("ol")); ol.append(el("li", {}, inline(oli[2]))); }
    else if (line.trim()) { ul = sub = ol = null; root.append(el("p", {}, inline(line.trim()))); }
  }
  return root;
}

async function page(id, into) {
  const e = await get(`/api/entity/${id}`);
  const box = el("div");
  if (e.has_map) box.append(el("a", {class: "maplink", href: `#/map/${id}`, text: "See its map →"}));
  box.append(markdown(e.markdown || `# ${e.label} (${id})`));
  into.replaceChildren(box);
  return e;
}

// ---------- the map ----------

function prepare(data, everyEdge) {
  // Which parts play which roles, so a provides edge the role's requires already says can be hidden, and a role's
  // interface its filler does not provide shows as missing.
  const plays = {}, requires = {}, provides = {};
  for (const e of data.edges) {
    if (e.kind === "plays") (plays[e.source] ||= []).push(e.target);
    if (e.kind === "requires") (requires[e.source] ||= new Set()).add(e.target);
    if (e.kind === "provides") (provides[e.source] ||= new Set()).add(e.target);
  }
  const implied = e => e.kind === "provides" && (plays[e.source] || []).some(r => requires[r] && requires[r].has(e.target));
  const edges = data.edges.filter(e => everyEdge || !implied(e)).map(e => ({...e}));
  let missing = 0;
  for (const [part, roles] of Object.entries(plays)) for (const r of roles) for (const i of requires[r] || []) {
    if (!(provides[part] && provides[part].has(i))) { edges.push({source: part, target: i, kind: "missing"}); missing++; }
  }
  return {edges, missing, hidden: data.edges.length - edges.filter(e => e.kind !== "missing").length};
}

function legend() {
  const box = $("legend");
  box.replaceChildren(...KINDS.map(k => el("span", {}, el("i", {class: k}), k)),
                      el("span", {}, el("i", {class: "missing"}), "missing"), el("span", {}, el("i", {class: "flagged"}), "flagged"));
}

async function map(id) {
  const data = await get(`/api/map/${id}`);
  current = id;
  $("crumb").textContent = `${data.label} (${id}) — map`;
  $("page").hidden = true; $("map").hidden = false; $("toolbar").hidden = false;
  legend();
  draw(data);
  $("all").onchange = () => draw(data);
  $("fit").onclick = () => cy && cy.fit(undefined, 30);
}

function draw(data) {
  const {edges, missing, hidden} = prepare(data, $("all").checked);
  if (cy) cy.destroy();
  const color = Object.fromEntries(KINDS.map(k => [k, css(`--${k}`)]));
  const lineColor = css("--muted"), text = css("--fg"), panel = css("--panel");
  cy = cytoscape({
    container: $("map"),
    elements: [
      ...data.nodes.map(n => ({data: {id: n.id, label: n.label, kind: n.kind}})),
      ...edges.map((e, i) => ({data: {id: `e${i}`, source: e.source, target: e.target, kind: e.kind, flagged: e.flagged ? 1 : 0}})),
    ],
    style: [
      {selector: "node", style: {shape: "round-rectangle", width: 180, height: 40, label: "data(label)", "text-wrap": "wrap",
        "text-max-width": 168, "text-valign": "center", "font-size": 11.5, color: "#fff", "background-color": n => color[n.data("kind")]}},
      {selector: "node[kind = 'whole']", style: {width: 200, height: 48, "font-size": 13, "font-weight": "bold"}},
      {selector: "node:selected", style: {"border-width": 3, "border-color": text}},
      {selector: "edge", style: {width: 1.2, "curve-style": "bezier", "target-arrow-shape": "triangle", "line-color": lineColor,
        "target-arrow-color": lineColor, label: "data(kind)", "font-size": 9, color: lineColor, "text-background-color": panel,
        "text-background-opacity": 1, "text-background-padding": 1}},
      {selector: "edge[kind = 'could-fill']", style: {"line-style": "dashed"}},
      {selector: "edge[kind = 'missing']", style: {"line-style": "dashed", "line-color": css("--missing"), "target-arrow-color": css("--missing"), color: css("--missing"), width: 2}},
      {selector: "edge[flagged = 1]", style: {"line-color": css("--flagged"), "target-arrow-color": css("--flagged"), color: css("--flagged"), width: 2.5}},
    ],
    layout: {name: "dagre", rankDir: "LR", nodeSep: 12, rankSep: 80, edgeSep: 8},
  });
  cy.on("tap", "node", ev => side(ev.target.id()));
  cy.on("dbltap", "node", ev => { if (ev.target.data("kind") === "part") location.hash = `#/map/${ev.target.id()}`; });
  cy.fit(undefined, 30);
  const n = data.nodes.length;
  $("stats").textContent = `${n} nodes · ${edges.length} edges` + (hidden ? ` · ${hidden} implied hidden` : "") + (missing ? ` · ${missing} missing` : "");
}

async function side(id) {
  $("side").hidden = false;
  await page(id, $("sidebody"));
  if (cy) cy.resize();
}
$("close").onclick = () => { $("side").hidden = true; if (cy) cy.resize(); };

// ---------- routes ----------

async function route() {
  $("list").hidden = false;
  const [, kind, id] = /^#\/(map|e)\/([QP][1-9][0-9]*)$/.exec(location.hash) || [];
  try {
    if (kind === "map") { await map(id); showWholes(id); }
    else if (kind === "e") {
      current = id;
      $("map").hidden = true; $("toolbar").hidden = true; $("page").hidden = false; $("side").hidden = true;
      const e = await page(id, $("page"));
      $("crumb").textContent = `${e.label} (${id})`;
      if (!$("q").value) showWholes(id);
    } else {
      current = null;
      $("map").hidden = true; $("toolbar").hidden = true; $("page").hidden = false; $("side").hidden = true;
      $("crumb").textContent = "";
      $("page").replaceChildren(el("div", {class: "md"}, el("h1", {text: "Maps in the store"}),
        el("p", {text: wholes.length ? "Pick a whole on the left to see it taken apart: its parts, the role each plays, and the interfaces roles require and parts provide. Click a node for its page; double-click a part to map it on its own." : "Nothing in the store has parts yet: map something with the map skill."})));
      showWholes(null);
    }
  } catch (err) {
    $("page").hidden = false; $("map").hidden = true; $("toolbar").hidden = true;
    $("page").replaceChildren(el("div", {class: "empty", text: `Could not load: ${err.message}`}));
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("load", async () => {
  cytoscape.use(cytoscapeDagre);
  try { wholes = await get("/api/wholes"); } catch { wholes = []; }
  route();
});
