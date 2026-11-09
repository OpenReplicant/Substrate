// What plugins add to the shell (README.md, "Client plugins"). Each kind has one small contract, and the core's
// own screens are registered through the same calls.
//
//   view       a screen that opens as a tab in the workspace: {id, title(params), icon, template | mount, key(params)}
//   widget     a card on the dashboard: {id, title, size: 's'|'m'|'l', template | mount, order}
//   inspector  a section of the right-hand pane for the current selection: {id, title, applies(sel), template | mount}
//   field      an editor for a JSON Schema property: {id, match(prop) -> score, template | mount}
//   command    something to run from the palette (Ctrl/Cmd+K): {id, title, run(wb), when(wb)?}
//   menu       a sidebar entry: {id, section, title, icon, open: [viewId, params], order}
//   app        another web UI, launched in the workspace: {id, title, icon, url, embed: 'frame' | 'window'}
//
// `template` names a <template id="..."> in the page (core/views.html, or a plugin's web/views.html, which the
// page includes at serve time); its root may use x-data with a component registered by wb.data(). `mount(el,
// ctx)` is the framework-free alternative: build into el, return a function that undoes it.

const kinds = ['view', 'widget', 'inspector', 'field', 'command', 'menu', 'app'];

export function createRegistry() {
  const items = Object.fromEntries(kinds.map((k) => [k, new Map()]));
  const listeners = new Set();
  const reg = {
    items,
    add(kind, def) {
      if (!items[kind]) throw new Error(`unknown kind ${kind}`);
      if (!def || !def.id) throw new Error(`a ${kind} needs an id`);
      items[kind].set(def.id, def);
      listeners.forEach((fn) => fn(kind, def));
      return def;
    },
    get(kind, id) { return items[kind].get(id); },
    list(kind) { return [...items[kind].values()].sort((a, b) => (a.order ?? 50) - (b.order ?? 50)); },
    onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  };
  return reg;
}

export { kinds };
