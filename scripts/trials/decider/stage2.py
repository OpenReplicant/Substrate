"""The decider trial, stage 2 (S-178): every decider on stage 1's cases, one result line each. Run in the trial image:

    scripts/trials/decider/run.sh

Deciders: `fast` (LFM3 1.7B's next-token probabilities, from stage 1), `vote` (S-170's embedding vote, k=3, leave one
out), `tabicl` (TabICL 2.2.0 on the embedding cut to 32 numbers by PCA, 4-fold: the other folds are the context),
`tabicl+fast` (the same with the fast model's eight probabilities as more columns), `gliner` (GLiNER2.5-Decide, zero
shot with the route descriptions), `vela` (vela3-fast, zero shot, the System One request). Measures: accuracy, ECE
(top label, 10 bins), Brier, median seconds per decision on this machine's CPU, and for TabICL a learning curve
(accuracy against labelled examples per route in its context): the online learning.
"""
import json, os, resource, statistics, sys, time
import numpy as np

S1 = json.load(open(os.environ.get("STAGE1", "/data/stage1.json")))
ROUTES, DESC, CASES = S1["routes"], S1["desc"], S1["cases"]
Y = np.array([ROUTES.index(c["route"]) for c in CASES])
X = np.array([c["embedding"] for c in CASES], dtype=np.float32)
X /= np.linalg.norm(X, axis=1, keepdims=True)
F = np.array([[c["fast"][r] for r in ROUTES] for c in CASES], dtype=np.float32)
ONLY = set(sys.argv[1:])


def report(name, P, secs, extra=""):
    P = np.asarray(P, dtype=np.float64)
    P = P / np.clip(P.sum(1, keepdims=True), 1e-12, None)
    pred, conf = P.argmax(1), P.max(1)
    hit = pred == Y
    ece = 0.0
    for lo in np.linspace(0, 1, 11)[:-1]:
        m = (conf > lo) & (conf <= lo + 0.1)
        if m.any():
            ece += m.mean() * abs(hit[m].mean() - conf[m].mean())
    brier = np.mean(np.sum((P - np.eye(len(ROUTES))[Y]) ** 2, 1))
    wrong = [f"{CASES[i]['text']!r}->{ROUTES[pred[i]]}" for i in np.where(~hit)[0]][:6]
    print(f"{name:12s} acc {hit.sum()}/{len(Y)} ({hit.mean():.3f})  ece {ece:.3f}  brier {brier:.3f}  "
          f"median {statistics.median(secs) * 1000:.0f} ms  rss {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024} MB {extra}")
    for w in wrong:
        print("     wrong:", w)
    sys.stdout.flush()


def want(n):
    return not ONLY or n in ONLY


if want("fast"):
    report("fast", F, [c["fast_s"] for c in CASES], "(via the gateway, stage 1)")

if want("vote"):
    S = X @ X.T
    P, secs = [], []
    for i in range(len(Y)):
        t = time.perf_counter()
        s = S[i].copy(); s[i] = -9
        top = np.argsort(-s)[:3]
        p = np.zeros(len(ROUTES))
        for j in top:
            p[Y[j]] += 1
        P.append(p); secs.append(time.perf_counter() - t + CASES[i]["embed_s"])
    report("vote", P, secs, "(+ embedding time)")

if want("tabicl") or want("tabicl+fast") or want("curve"):
    from sklearn.decomposition import PCA
    from tabicl import TabICLClassifier

    def tab(train, test, feats):
        pca = PCA(n_components=min(32, len(train) - 1), random_state=0).fit(X[train])
        A = lambda idx: np.hstack([pca.transform(X[idx])] + ([F[idx]] if feats else []))
        clf = TabICLClassifier(random_state=0, device="cpu")
        clf.fit(A(train), Y[train])
        t = time.perf_counter(); p = clf.predict_proba(A(test)); dt = (time.perf_counter() - t) / len(test)
        full = np.zeros((len(test), len(ROUTES)))
        full[:, clf.classes_] = p
        return full, dt

    rng = np.random.default_rng(0)
    folds = np.array_split(rng.permutation(len(Y)), 4)
    for name, feats in (("tabicl", False), ("tabicl+fast", True)):
        if not want(name):
            continue
        P, secs = np.zeros((len(Y), len(ROUTES))), []
        for k in range(4):
            test = folds[k]; train = np.concatenate([folds[j] for j in range(4) if j != k])
            p, dt = tab(train, test, feats)
            P[test] = p
            secs += [dt + CASES[i]["embed_s"] + (CASES[i]["fast_s"] if feats else 0) for i in test]
        report(name, P, secs, "(4-fold; + embedding" + (" + fast)" if feats else ")"))
    if want("curve"):
        for n in (1, 2, 4, 8):
            accs = []
            for rep in range(5):
                r = np.random.default_rng(rep)
                train = np.concatenate([r.choice(np.where(Y == c)[0], n, replace=False) for c in range(len(ROUTES))])
                test = np.setdiff1d(np.arange(len(Y)), train)
                p, _ = tab(train, test, False)
                accs.append((p.argmax(1) == Y[test]).mean())
            print(f"curve        tabicl with {n} example(s) per route in context: acc {np.mean(accs):.3f} (5 draws, min {min(accs):.3f})")
            sys.stdout.flush()

if want("gliner"):
    from gliner2 import AutoExtractor
    m = AutoExtractor.from_pretrained("fastino/GLiNER2.5-Decide", revision=os.environ["GLINER_REV"])
    task = {"route": {"labels": DESC}}
    P, secs = [], []
    for c in CASES:
        t = time.perf_counter()
        out = m.classify_text(c["text"], task, threshold=0.0, include_confidence=True)
        secs.append(time.perf_counter() - t)
        if len(P) == 0:
            print("gliner sample:", json.dumps(out)[:300])
        p = np.zeros(len(ROUTES))
        got = out.get("route", out)
        items = got if isinstance(got, list) else [got]
        for it in items:
            if isinstance(it, dict) and it.get("label") in ROUTES:
                p[ROUTES.index(it["label"])] = max(p[ROUTES.index(it["label"])], float(it.get("confidence", 1.0)))
            elif isinstance(it, str) and it in ROUTES:
                p[ROUTES.index(it)] = 1.0
        P.append(p if p.sum() else np.ones(len(ROUTES)))
    report("gliner", P, secs, "(zero shot, CPU)")

if want("vela"):
    path = os.environ["VELA_PATH"]
    sys.path.insert(0, path)
    from vela3_encoder import Vela3Encoder
    m = Vela3Encoder.load(path)
    q = {"route": {"type": "choice", "instructions": "Which route should handle this spoken request to a voice assistant?",
                   "criteria": DESC}}
    P, secs = [], []
    for c in CASES:
        t = time.perf_counter(); out = m.system_one(c["text"], q); secs.append(time.perf_counter() - t)
        if len(P) == 0:
            print("vela sample:", json.dumps(out, default=str)[:300])
        a = out["answers"]["route"]
        probs = a.get("probabilities") or a.get("probs") or a.get("distribution") or {}
        P.append([float(probs.get(r, 0.0)) for r in ROUTES] if probs else np.eye(len(ROUTES))[ROUTES.index(a.get("choice"))])
    report("vela", P, secs, "(zero shot, CPU)")
