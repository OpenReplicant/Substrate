window.draw = (data, el) => new Promise(resolve => {
  const cy = cytoscape({
    container: el,
    elements: [...data.nodes.map(n => ({data: {id: n.id, label: n.label, kind: n.kind}})),
               ...data.edges.map((e, i) => ({data: {id: "e" + i, source: e.source, target: e.target, kind: e.kind}}))],
    style: [
      {selector: "node", style: {shape: "round-rectangle", width: 170, height: 38, label: "data(label)", "text-wrap": "wrap",
        "text-max-width": 160, "text-valign": "center", "font-size": 11, color: "#fff",
        "background-color": e => KIND[e.data("kind")]}},
      {selector: "edge", style: {width: 1.2, "curve-style": "bezier", "target-arrow-shape": "triangle", "line-color": "#999",
        "target-arrow-color": "#999", label: "data(kind)", "font-size": 9, color: "#555", "text-background-color": "#fff",
        "text-background-opacity": 1}},
      {selector: "edge[kind = 'could-fill']", style: {"line-style": "dashed"}},
    ],
    layout: {name: "dagre", rankDir: "LR", nodeSep: 14, rankSep: 90},
  });
  cy.ready(() => resolve(cy.nodes().map(n => { const b = n.renderedBoundingBox({includeLabels: false}); return {id: n.id(), x1: b.x1, y1: b.y1, x2: b.x2, y2: b.y2}; })));
});
