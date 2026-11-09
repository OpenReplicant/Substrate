"""rdflib with OWL-RL's RDFS closure, in process: load the export and the vocabulary, expand, run the queries.
Run inside python:3.13-slim with rdflib and owlrl installed (run.sh does it). Prints one JSON line per query."""
import json
import sys
import time
from pathlib import Path

import owlrl
from rdflib import Graph

here = Path(sys.argv[1])
t0 = time.monotonic()
g = Graph()
g.parse(here / "data.nt", format="nt")
g.parse(here / "vocab.ttl", format="turtle")
loaded = time.monotonic()
owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(g)
print(json.dumps({"load_s": round(loaded - t0, 2), "closure_s": round(time.monotonic() - loaded, 2), "triples": len(g)}))
for q in sorted(here.glob("q*.rq")):
    t = time.monotonic()
    rows = [[str(v) for v in r] for r in g.query(q.read_text())]
    print(json.dumps({"query": q.name, "rows": rows[:3], "n": len(rows), "s": round(time.monotonic() - t, 3)}))
