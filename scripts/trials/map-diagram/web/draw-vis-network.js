window.draw = (data, el) => new Promise(resolve => {
  const nodes = data.nodes.map(n => ({id: n.id, label: n.label, shape: "box", color: KIND[n.kind], font: {color: "#fff", size: 11},
    widthConstraint: {minimum: 150, maximum: 170}, heightConstraint: {minimum: 26}}));
  const edges = data.edges.map(e => ({from: e.source, to: e.target, label: e.kind, arrows: "to", dashes: e.kind === "could-fill",
    font: {size: 9, align: "middle"}, color: "#999"}));
  const net = new vis.Network(el, {nodes, edges}, {physics: false,
    layout: {hierarchical: {direction: "LR", sortMethod: "directed", levelSeparation: 230, nodeSpacing: 50}}});
  net.once("afterDrawing", () => resolve(data.nodes.map(n => { const b = net.getBoundingBox(n.id); return {id: n.id, x1: b.left, y1: b.top, x2: b.right, y2: b.bottom}; })));
});
