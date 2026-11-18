"""One line per candidate and case set from results.jsonl: the trial's output for the owner and the store."""
import json
import statistics as st
import sys
from collections import defaultdict

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
# re-score from the kept transcripts with trial.py's current normalisation, when its references can be read
if len(sys.argv) > 2:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    import trial
    from pathlib import Path
    refs = {f"librispeech:{i}": t for i, _, _, t in trial.librispeech(Path(sys.argv[2]))}
    for r in rows:
        if "hyp" in r:
            ref = refs.get(r["case"]) or trial.SENTENCES[int(r["case"].rsplit("/", 1)[1])]
            r["wer"] = round(trial.wer(ref, r["hyp"]), 3)
by = defaultdict(lambda: defaultdict(list))
meta = defaultdict(dict)
for r in rows:
    c, case = r["candidate"], r["case"]
    if case in ("load", "peak_rss_mb", "failed"):
        meta[c][case] = r.get("seconds", r.get("value", True))
    else:
        by[c][case.split(":", 1)[0] if not case.startswith("roundtrip") else "roundtrip:" + case.split(":")[1].split("/")[0]].append(r)
p = lambda xs, q: round(sorted(xs)[min(len(xs) - 1, int(q * len(xs)))], 3) if xs else None
for c in sorted(set(meta) | set(by)):
    m = meta[c]
    print(f"{c}: load {m.get('load')} s, peak memory {m.get('peak_rss_mb')} MB" + (" — FAILED" if m.get("failed") else ""))
    for k, rs in sorted(by[c].items()):
        line = f"  {k:28s} n={len(rs):3d}"
        if "wer" in rs[0]:
            words = sum(len(x.get('hyp', '').split()) for x in rs)
            line += f"  WER mean {st.mean(x['wer'] for x in rs):.3f}  rtf median {p([x['rtf'] for x in rs], .5)}  seconds p50 {p([x['seconds'] for x in rs], .5)} p95 {p([x['seconds'] for x in rs], .95)}"
        if "rtf" in rs[0] and "wer" not in rs[0]:
            line += f"  rtf median {p([x['rtf'] for x in rs], .5)}  whole clip p50 {p([x['seconds'] for x in rs], .5)} s"
        fa = [x["first_audio_s"] for x in rs if x.get("first_audio_s") is not None]
        if fa:
            line += f"  first audio p50 {p(fa, .5)} s max {max(fa)} s"
        print(line)
