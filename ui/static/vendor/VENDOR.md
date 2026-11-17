# Vendored browser files

Served from the UI's own origin, so its CSP needs no other source. Picked for the UI's map diagram (role Q144 in
the store; DECISIONS.md S-140); the trial is `scripts/trials/map-diagram/`. Each file is from its npm tarball,
checked against the registry's sha512 (`scripts/trials/map-diagram/fetch.py`), and its SHA-256 here is checked by
`scripts/tests/test_ui.py`.

| File | Package | Licence | SHA-256 |
| --- | --- | --- | --- |
| `cytoscape/cytoscape.min.js` | cytoscape 3.34.4 (2026-10-15) | MIT (`cytoscape/LICENSE`) | `081591ab735b2b6a3b31a3c60f8f3a3e2fee8c92939e0c7820ad1208571b6cd8` |
| `cytoscape-dagre/cytoscape-dagre.min.js` | cytoscape-dagre 4.0.1 (2026-08-28; its banner says 4.0.0), dagre bundled | MIT (`cytoscape-dagre/LICENSE`) | `ec671a41d2bfcac580352e2997797793949e3489cecaf347fc48670d4bd456b0` |

Cytoscape injects one rule as an inline style element unless an element with id `__________cytoscape_stylesheet`
exists; `../cytoscape.css` carries that rule and the page links it under that id.
