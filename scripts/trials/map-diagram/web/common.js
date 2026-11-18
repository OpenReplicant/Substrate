// Loads ?case=NAME, calls window.draw(data, el) (each candidate's file), and leaves window.__result for run.py:
// whether it drew, how long it took, every node's box (for overlaps) and any CSP violation.
const KIND = {whole: "#37474f", part: "#2e7d32", role: "#b26a00", interface: "#1565c0", candidate: "#8e8e8e"};
const violations = [];
document.addEventListener("securitypolicyviolation", e => violations.push(e.violatedDirective + " " + (e.blockedURI || "inline")));
window.addEventListener("load", async () => {
  const name = new URLSearchParams(location.search).get("case");
  const data = await (await fetch(`cases/${name}.json`)).json();
  const el = document.getElementById("map");
  const t0 = performance.now();
  try {
    const boxes = await window.draw(data, el);
    window.__result = {ok: true, ms: Math.round(performance.now() - t0), nodes: data.nodes.length, boxes, violations};
  } catch (e) {
    window.__result = {ok: false, error: String(e && e.stack || e), violations};
  }
});
