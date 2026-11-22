"""An organization as an environment: its history replayed day by day, the people and agents in it as actors that
can be interviewed (exploration) or delegated to (exploitation), and a principal whose goals it serves.

Mining (`python3 -m envkit.org mine CLONES OUT`) reads bare git clones of the org's repositories and writes one event
per line: commits with their author, co-authors and session (from commit trailers), the top-level areas touched, and
each repository's own description of itself (its README's first line). Forks keep only commits by the org's own
actors (the authors of its original repositories); the rest is counted as upstream. Author emails are not kept. The
snapshot is the org's data: it stays on the machine (`orgdata/` is ignored by git) and the declaration names it by a
variable.

The world (driver `org`): one tick a day. Outputs: `events` (that day's events, a list), `repos` (once, at the start:
each repository's description), `reply` (answers to interviews), `tick`. Input: `cmd`, a command
{"action": "interview", "params": {"who": actor, "question": text}} or {"action": "delegate", "params": {"who":
actor, "task": text}}, or {"action": "wait"}. The start event names the replay's first and last day (`day`, `until`): an agent can catch up on
the history before it acts, in the `present` days that follow it (no new history; the time to ask and delegate). Interviews go to a mailbox directory: `questions/<id>.json` for the
person to answer, `answers/<id>.json` when they have (the id is a hash of who and the question, so asking again
finds the answer). A replay runs in seconds and people answer in hours, so an answer reaches the run that asks
after it was given. Delegation is recorded, with no outcome yet: acting in the org is a later step, and the
principal's.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from envkit.core import Msg, Port, World

DAY = 86400
SEP = "\x1e"  # between fields
REC = "\x1d"  # before each commit


def _git(repo: Path, *args) -> str:
    return subprocess.run(["git", f"--git-dir={repo}", *args], capture_output=True, text=True, check=True).stdout


def mine(clones: Path, out: Path, skip=("morphogen-judge",), forks=("cognee-enhanced", "webClient-VAD-faster-whisper")):
    repos = sorted(p for p in clones.glob("*.git") if p.stem not in skip)
    fmt = SEP.join(["%H", "%at", "%an", "%s", "%(trailers:key=Co-Authored-By,valueonly,separator=|)",
                    "%(trailers:key=Claude-Session,valueonly)", "%P"])
    raw = {}
    for r in repos:
        text = _git(r, "log", "--all", f"--format={REC}{fmt}", "--name-only", "--no-renames")
        commits = []
        for chunk in text.split(REC)[1:]:
            head, _, files = chunk.partition("\n")
            sha, at, an, subj, co, sess, parents = (head.split(SEP) + [""] * 7)[:7]
            areas = sorted({f.split("/")[0] for f in files.split("\n") if f.strip()})
            commits.append({"repo": r.stem, "sha": sha[:10], "t": int(at), "author": an.strip(),
                            "coauthors": sorted({re.sub(r"\s*<.*", "", c).strip() for c in co.split("|") if c.strip()}),
                            "session": sess.strip().rsplit("/", 1)[-1] or None, "subject": subj[:200],
                            "areas": areas[:20], "merge": len(parents.split()) > 1})
        raw[r.stem] = commits
    own = {c["author"] for name, cs in raw.items() if name not in forks for c in cs}
    events, upstream = [], Counter()
    for name, cs in raw.items():
        for c in cs:
            if name in forks and c["author"] not in own:  # upstream work, even with a co-author the org also has
                upstream[name] += 1
                continue
            events.append({"kind": "merge" if c.pop("merge") else "commit", **c})
    for r in repos:
        desc = ""
        for readme in ("README.md", "readme.md", "README"):
            try:
                lines = _git(r, "show", f"HEAD:{readme}").splitlines()
            except subprocess.CalledProcessError:
                continue
            body = [ln.strip() for ln in lines if ln.strip() and not ln.startswith(("#", "!", "[", "<", "```"))]
            desc = body[0][:300] if body else ""
            break
        first = min((e["t"] for e in events if e["repo"] == r.stem), default=None)
        events.append({"kind": "repo", "repo": r.stem, "t": first or 0, "description": desc,
                       "fork": r.stem in forks, "upstream_commits": upstream[r.stem]})
    events.sort(key=lambda e: (e["t"], e["kind"] != "repo"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(e) + "\n" for e in events))
    return len(events), len(own)


def qid(who: str, question: str) -> str:
    return hashlib.sha256(f"{who}\n{question}".encode()).hexdigest()[:12]


class OrgWorld(World):
    inputs = {"cmd": Port("command", keep="all")}

    def __init__(self, name, snapshot: str, mailbox: str, principal: str = "principal", start: str | None = None,
                 end: str | None = None, present: int = 7, rate: float = 20.0):
        self.outputs = {"events": Port("event", keep="all"), "repos": Port("json", keep="all"),
                        "reply": Port("event", keep="all"), "actions": Port("event", keep="all"),
                        "tick": Port("event"), "event": Port("event", keep="all"), "reward": Port("scalar", keep="all")}
        super().__init__(name)
        if not snapshot or not Path(snapshot).exists():
            raise FileNotFoundError(f"{name}: no org snapshot at {snapshot!r} (python3 -m envkit.org mine ...)")
        self.events = [json.loads(ln) for ln in Path(snapshot).read_text().splitlines()]
        self.mailbox, self.principal, self.rate = Path(mailbox), principal, rate
        import datetime as dt
        day = lambda s: int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp()) // DAY  # noqa: E731
        days = [e["t"] // DAY for e in self.events if e["t"]]
        self.d0 = day(start) if start else min(days)
        self.d1 = day(end) if end else max(days)
        self.i, self.asked, self.log, self.present = 0, set(), [], int(present)

    def start(self):
        for d in ("questions", "answers"):
            (self.mailbox / d).mkdir(parents=True, exist_ok=True)

    def on(self, port, msg: Msg):
        c = msg.data or {}
        a, p = c.get("action"), c.get("params") or {}
        if a == "interview":
            q = qid(p["who"], p["question"])
            self.asked.add(q)
            path = self.mailbox / "questions" / f"{q}.json"
            if not path.exists():
                path.write_text(json.dumps({"id": q, "who": p["who"], "question": p["question"],
                                            "asked_on_day": self.today, "why": p.get("why", "")}, indent=1))
            self.log.append(("interview", p["who"], p["question"]))
        elif a == "delegate":
            self.log.append(("delegate", p["who"], p.get("task")))

    def _replies(self):
        out = []
        for q in sorted(self.asked):
            a = self.mailbox / "answers" / f"{q}.json"
            if a.exists():
                out.append({"id": q, **json.loads(a.read_text())})
                self.asked.discard(q)
        return out

    def tick(self, t: int):
        self.today = self.d0 + t
        if t == 0:
            self.emit("actions", {"names": ["wait", "interview", "delegate"], "points": [False, False, False]})
            self.emit("event", {"kind": "start", "day": self.today, "until": self.d1})
            self.emit("repos", [e for e in self.events if e["kind"] == "repo"])
            # answers given since an earlier run: every question already in the mailbox, answered
            for a in sorted((self.mailbox / "answers").glob("*.json")):
                self.asked.add(a.stem)
        today = []
        while self.i < len(self.events) and self.events[self.i]["t"] // DAY <= self.today:
            e = self.events[self.i]
            if e["kind"] != "repo":
                today.append(e)
            self.i += 1
        self.emit("events", today)
        for r in self._replies():
            self.emit("reply", r)
        self.emit("reward", 0.0)
        self.emit("tick", {"day": self.today})
        if self.today >= self.d1 + self.present:  # the history, then a few days of the present to act in
            self.done = True
            self.emit("event", {"kind": "end", "steps": t, "interviews": sum(1 for x in self.log if x[0] == "interview")})


# --- adapters into the workspace: entity resolution, mechanical and fair ----------------------------------------


def resolve(events, t):
    """Each day's events: an entry per event (gone the next day) and the actors and repositories they touch, with
    running counts (the mechanical part of the map; what they mean is the cartographer's)."""
    out = []
    for e in events:
        if e["kind"] not in ("commit", "merge"):
            continue
        out.append({"key": f"commit:{e['repo']}:{e['sha']}", "kind": "commit", "ttl": 1, "attrs": e})
        for who, role in [(e["author"], "author")] + [(c, "coauthor") for c in e["coauthors"]]:
            out.append({"key": f"actor:{who}", "kind": "actor",
                        "attrs": {"last_day": e["t"] // DAY, f"last_{role}_repo": e["repo"]}})
    return out


def repos(data, t):
    return [{"key": f"repo:{r['repo']}", "kind": "repo",
             "attrs": {"description": r["description"], "fork": r["fork"], "upstream_commits": r["upstream_commits"]}}
            for r in data]


def reply(data, t):
    return [{"key": f"reply:{data['id']}", "kind": "reply", "salience": 1.0, "attrs": data}]


REPOS = ("Alpine-Handlebars", "DiscordPrototype", "Hyperexpress-MiddleWrap", "MetaSoar", "Morphogen",
         "ProtoReplicant", "Substrate", "actor-model", "cognee-enhanced", "kernel", "openreplicant.github.io",
         "webClient-VAD-faster-whisper")  # never morphogen-judge: its held-out cases are not to be read


def fetch(home: Path, org: str = "OpenReplicant", repos=REPOS):
    """Bare clones of the org's repositories under home/clones, history only (file contents on demand)."""
    (home / "clones").mkdir(parents=True, exist_ok=True)
    for r in repos:
        d = home / "clones" / f"{r}.git"
        if d.exists():
            subprocess.run(["git", f"--git-dir={d}", "fetch", "-q", "--prune", "origin",
                            "+refs/heads/*:refs/heads/*"], check=False)
        else:
            subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:none",
                            f"https://github.com/{org}/{r}.git", str(d)], check=False)


def map_org(home: Path, end: str = "", present: int = 7, ask: bool = True):
    """Run the cartographer over the snapshot up to `end` (default: today) and return it. With ask=False it
    writes nothing to the mailbox (a held-out run must not ask about the past)."""
    import os
    import datetime as dt
    os.environ["ORG_SNAPSHOT"], os.environ["ORG_MAILBOX"] = str(home / "openreplicant.jsonl"), str(home / "mailbox")
    end = end or dt.date.today().isoformat()
    from envkit import run as R
    from envkit.run import run
    box = {}
    real = R.AGENTS["cartographer"]

    def keep(seed, **o):  # keep the agent, to read its map after the run
        a = real(seed, **o)
        box["agent"] = a
        return a
    R.AGENTS["cartographer"] = keep
    try:
        out = run("openreplicant", {"end": end, "present": present}, agent="cartographer", profile="member",
                  agent_opts=None if ask else {"budget": 0})
    finally:
        R.AGENTS["cartographer"] = real
    return box["agent"].policy, out


def brief(home: Path, end: str = "", offline: bool = False):
    import datetime as dt
    if not offline:
        fetch(home)
    n, own = mine(home / "clones", home / "openreplicant.jsonl")
    carto, _ = map_org(home, end)
    text = carto.report()
    day = end or dt.date.today().isoformat()
    (home / "map.md").write_text(text)
    (home / "briefs").mkdir(exist_ok=True)
    (home / "briefs" / f"{day}.md").write_text(text)
    return text, n


def answer(home: Path, q: str, text: str):
    path = home / "mailbox" / "questions" / f"{q}.json"
    if not path.exists():
        raise SystemExit(f"no question {q} in {home / 'mailbox' / 'questions'}")
    (home / "mailbox" / "answers").mkdir(parents=True, exist_ok=True)
    (home / "mailbox" / "answers" / f"{q}.json").write_text(json.dumps({"answer": text}, indent=1))


def holdout(home: Path, cuts, horizon: int = 28):
    """The map judged on time it has not seen: learn the record up to each cut, forecast which repositories see
    work in the `horizon` days after, score against what happened (Brier: 0 is perfect, 0.25 is a coin). The
    baseline forecasts every repository at the share that were active."""
    import datetime as dt
    events = [json.loads(ln) for ln in (home / "openreplicant.jsonl").read_text().splitlines()]
    rows = []
    for cut in cuts:
        carto, _ = map_org(home, cut, present=0, ask=False)
        c = int(dt.datetime.fromisoformat(cut).replace(tzinfo=dt.timezone.utc).timestamp()) // DAY
        f = carto.predict(horizon)
        actual = {r: any(e["repo"] == r and c < e["t"] // DAY <= c + horizon and e["kind"] != "repo"
                         for e in events) for r in f}
        base = sum(actual.values()) / max(1, len(actual))
        brier = sum((f[r] - actual[r]) ** 2 for r in f) / max(1, len(f))
        b0 = sum((base - actual[r]) ** 2 for r in f) / max(1, len(f))
        hits = sum((f[r] >= 0.5) == actual[r] for r in f)
        rows.append({"cut": cut, "repos": len(f), "active_after": sum(actual.values()), "brier": round(brier, 3),
                     "baseline_brier": round(b0, 3), "right": f"{hits}/{len(f)}"})
    return rows


def main(argv=None):
    import argparse
    import os
    ap = argparse.ArgumentParser(prog="python3 -m envkit.org")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("mine", help="mine bare clones into a snapshot")
    m.add_argument("clones")
    m.add_argument("out")
    home = os.environ.get("ORG_HOME", "orgdata")
    b = sub.add_parser("brief", help="fetch, mine and map the org; write map.md and briefs/DATE.md under ORG_HOME")
    b.add_argument("--end", default="", help="map up to this date (default today)")
    b.add_argument("--offline", action="store_true", help="use the clones as they are")
    sub.add_parser("questions", help="the questions waiting on the principal")
    an = sub.add_parser("answer", help="answer a question: answer ID TEXT")
    an.add_argument("id")
    an.add_argument("text", nargs="+")
    h = sub.add_parser("holdout", help="score the map's forecasts on time it has not seen")
    h.add_argument("cuts", nargs="+", help="dates to cut the record at")
    h.add_argument("--horizon", type=int, default=28)
    a = ap.parse_args(argv)
    home = Path(home)
    if a.cmd == "mine":
        n, own = mine(Path(a.clones), Path(a.out))
        print(f"{n} events, {own} of the org's own actors")
    elif a.cmd == "brief":
        text, n = brief(home, a.end, a.offline)
        print(text)
    elif a.cmd == "questions":
        for q in sorted((home / "mailbox" / "questions").glob("*.json")):
            if not (home / "mailbox" / "answers" / q.name).exists():
                d = json.loads(q.read_text())
                print(f"{d['id']}  {d['question']}")
    elif a.cmd == "answer":
        answer(home, a.id, " ".join(a.text))
        print("saved; the next brief reads it")
    elif a.cmd == "holdout":
        for row in holdout(home, a.cuts, a.horizon):
            print(json.dumps(row))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
