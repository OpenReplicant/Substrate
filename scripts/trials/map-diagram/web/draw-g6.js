window.draw = async (data, el) => {
  const graph = new G6.Graph({
    container: el, autoFit: "view",
    data: {nodes: data.nodes.map(n => ({id: n.id, data: n})), edges: data.edges.map((e, i) => ({id: "e" + i, source: e.source, target: e.target, data: e}))},
    node: {type: "rect", style: {size: [170, 38], radius: 6, fill: d => KIND[d.data.kind], labelText: d => d.data.label,
      labelPlacement: "center", labelFill: "#fff", labelFontSize: 11, labelWordWrap: true, labelMaxWidth: 160}},
    edge: {type: "polyline", style: {endArrow: true, stroke: "#999", labelText: d => d.data.kind, labelFontSize: 9,
      lineDash: d => d.data.kind === "could-fill" ? [4, 3] : 0}},
    layout: {type: "dagre", rankdir: "LR", nodesep: 14, ranksep: 90},
  });
  await graph.render();
  return data.nodes.map(n => { const b = graph.getElementRenderBounds(n.id); return {id: n.id, x1: b.min[0], y1: b.min[1], x2: b.max[0], y2: b.max[1]}; });
};
