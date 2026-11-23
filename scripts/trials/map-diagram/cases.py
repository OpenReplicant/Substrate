"""The trial's cases as JSON (nodes with kind, edges with kind) in .state/trials/map-diagram/cases/:
substrate.json is Substrate's own map from the kernel, read through the UI's API (/api/map/Q10, the real data; the UI
must be up, scripts/up.sh);
wide.json is a synthetic map ten times its size (a whole, 4 subsystems of 12 parts, a role each, interfaces
shared between roles, 2 candidates per subsystem), for how the layout copes as maps grow.

    bin/in-tools python3 scripts/trials/map-diagram/cases.py
"""
import json, os, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
UI = os.environ.get("UI_URL", "http://127.0.0.1:8100")

OUT = ROOT / ".state/trials/map-diagram/cases"
OUT.mkdir(parents=True, exist_ok=True)

with urllib.request.urlopen(f"{UI}/api/map/Q10", timeout=30) as r:
    got = json.load(r)
nodes = [{"id": n["id"], "label": n["label"], "kind": n["kind"]} for n in got["nodes"]]
edges = [{"source": e["source"], "target": e["target"], "kind": e["kind"]} for e in got["edges"]]
(OUT / "substrate.json").write_text(json.dumps({"nodes": nodes, "edges": edges}))

N, E = [{"id": "W", "label": "a whole", "kind": "whole"}], []
for s in range(4):
    sub = f"S{s}"
    N.append({"id": sub, "label": f"subsystem {s}", "kind": "part"}); E.append({"source": "W", "target": sub, "kind": "has-part"})
    for p in range(12):
        part, role = f"{sub}P{p}", f"{sub}R{p}"
        N += [{"id": part, "label": f"part {s}.{p} with a longer name", "kind": "part"},
              {"id": role, "label": f"role {s}.{p}", "kind": "role"}]
        E += [{"source": sub, "target": part, "kind": "has-part"}, {"source": part, "target": role, "kind": "plays"}]
        for i in {p % 5, (p + s) % 7 + 5}:
            E += [{"source": role, "target": f"I{i}", "kind": "requires"}, {"source": part, "target": f"I{i}", "kind": "provides"}]
    for k in range(2):
        cand = f"{sub}C{k}"
        N.append({"id": cand, "label": f"candidate {s}.{k}", "kind": "candidate"})
        E.append({"source": cand, "target": f"{sub}R{k}", "kind": "could-fill"})
N += [{"id": f"I{i}", "label": f"interface {i}", "kind": "interface"} for i in range(12)]
(OUT / "wide.json").write_text(json.dumps({"nodes": N, "edges": E}))
print(f"substrate: {len(nodes)} nodes, {len(edges)} edges; wide: {len(N)} nodes, {len(E)} edges")
