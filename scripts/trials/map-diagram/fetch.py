"""Fetch each candidate's browser files from npm, checked against the sha512 pinned here, into
.state/trials/map-diagram/vendor/<name>/ (the UI's map diagram, research skill step 3).

    bin/in-tools python3 scripts/trials/map-diagram/fetch.py
"""
import base64, hashlib, io, sys, tarfile, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / ".state/trials/map-diagram/vendor"
# name: (tarball, its npm integrity, the files a page loads) — read from registry.npmjs.org 2026-11-17
PACKAGES = {
    "cytoscape": ("https://registry.npmjs.org/cytoscape/-/cytoscape-3.34.4.tgz",
                  "sha512-msY99tMY8iWTg+sIPGfSqDcPNOt4xcj+v/K/7qUFaCUxxlqnMkUYLBjRUzn9W5CU/R2hrmtJa5+UtovrEM2ctg==",
                  ["dist/cytoscape.min.js"]),
    "cytoscape-dagre": ("https://registry.npmjs.org/cytoscape-dagre/-/cytoscape-dagre-4.0.1.tgz",
                        "sha512-hyNdh8Vp1nwzBcjHnM4c71G81bFhPmQYLXD2HM9AZIvl+8TrMzWEOPW45hF/XOBQiEguPcDQzi6VrXR1XBcXOA==",
                        ["dist/cytoscape-dagre.min.js"]),
    "mermaid": ("https://registry.npmjs.org/mermaid/-/mermaid-12.2.0.tgz",
                "sha512-w7nr/SFrLO7BaVTs3dQTvYSV6nYSBj0Yy9DjBhsIJtAcHqRzXSq4Pg32ujHZ/AdWsAMNEvvhbm5dt9E2tOiHzw==",
                ["dist/mermaid.min.js"]),
    "vis-network": ("https://registry.npmjs.org/vis-network/-/vis-network-10.1.4.tgz",
                    "sha512-WWt7Sjenxt7dJL54gty7AUtkW2UugRt+4TFoONubMGFDHD2cer2thDOPTpM9KKLRSvAoZ42FwWN3lvv0I02SKw==",
                    ["standalone/umd/vis-network.min.js"]),
    "g6": ("https://registry.npmjs.org/@antv/g6/-/g6-5.1.1.tgz",
           "sha512-50bXxMUf4mChyOv4ePVeWZLwotih9VunKfp0a++Wofv/wCyY8fb9+CV2wouIBCOZnd5ydBRA4NNaX9yLJzqa2w==",
           ["dist/g6.min.js"]),
}

for name, (url, integrity, files) in PACKAGES.items():
    data = urllib.request.urlopen(url, timeout=120).read()
    got = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
    if got != integrity:
        sys.exit(f"{name}: integrity mismatch ({got})")
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        for f in files + ["LICENSE"]:
            try:
                m = t.extractfile("package/" + f)
            except KeyError:
                continue
            (d / Path(f).name).write_bytes(m.read())
    print(f"{name}: ok, {', '.join(f'{Path(f).name} {(d / Path(f).name).stat().st_size} bytes' for f in files)}")

# What each bundle carries besides itself: ELK (Eclipse Public License) is ruled out by the licence rule, so a
# bundle containing it is too, whatever its own package's licence says.
lines = []
for name, (_, _, files) in PACKAGES.items():
    text = "".join((OUT / name / Path(f).name).read_text(errors="replace") for f in files)
    lines.append(f"{name}: org.eclipse={text.count('org.eclipse')} elk.algorithm={text.count('elk.algorithm')} "
                 f"new_Function={text.count('new Function(')}")
(OUT.parent / "bundles.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
