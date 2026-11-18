"""Medians per condition from contention.py's results."""
import json
import statistics as st
import sys
from collections import defaultdict

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
voice, model = defaultdict(list), defaultdict(list)
for r in rows:
    if "voice" in r:
        voice[(r["voice"], r["kind"], r["condition"])].append(r)
    else:
        model[r["condition"]].append(r)
med = lambda xs: round(st.median(xs), 3) if xs else None  # noqa: E731
print("the local model (300-token answer):")
for c, rs in sorted(model.items()):
    print(f"  {c:22s} n={len(rs)}  first token {med([r['first_token_s'] for r in rs])} s  tokens/s {med([r['tokens_per_s'] for r in rs if r['tokens_per_s']])}")
print("the voice:")
for (v, k, c), rs in sorted(voice.items()):
    print(f"  {v} {k:8s} {c:18s} n={len(rs):2d}  first audio {med([r['first_audio_s'] for r in rs])} s (max {max(r['first_audio_s'] for r in rs)})  whole {med([r['whole_s'] for r in rs])} s")
