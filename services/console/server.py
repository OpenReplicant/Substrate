"""Substrate's console (S-22): one page, live state, kernel sign-in.

Runs in kernel's image (Python, Starlette, uvicorn, psycopg, PyYAML are already there; HTTP is the standard library's) behind the front
door at /console/ (deploy/caddy/Caddyfile). Nothing new holds a password: a person signs in with their kernel
login (`kk person add`; `kk up` prints the owner's), kernel checks it at /ui/login and returns a bearer token,
and the console keeps that token in an HttpOnly cookie. Every request is checked by asking kernel `whoami`
with it, and kernel decides what the person may see and review (clearance is Postgres's, kernel invariant 4).

What it reads, all read-only except the two owner actions:
  kernel       review_queue, review (approve/decline) and whoami, over MCP with the person's own token
  Prometheus   gateway spend and tokens (Bifrost's metrics)
  each service its health endpoint
  the bus      queue depths, proposed goals; a proposed goal is sent to the `owner` queue
  /substrate   this checkout, read-only: docs/build.yaml (spec progress), catalog-info.yaml, repos.yaml,
               the clones' git refs, Morphogen's evidence log (.git/morphogen/evidence.db)

    python3 server.py        # settings from the environment, see SETTINGS
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import psycopg
import uvicorn
import yaml
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

SETTINGS = {
    "KERNEL_URL": "http://kernel:8000",
    "BIFROST_URL": "http://bifrost:8080",
    "BACKSTAGE_URL": "http://backstage:7007",
    "PROMETHEUS_URL": "http://prometheus:9090",
    "NOMAD_ADDR": "",                 # set under RUNTIME=nomad
    "BUS_URL": "postgresql://substrate_bus@db:5432/substrate",
    "SUBSTRATE_BUS_PASSWORD": "",
    "SUBSTRATE_ROOT": "/substrate",
    "RUNTIME": "compose",
    "CONTAINER_ENGINE": "podman",
    "CONSOLE_HOST": "0.0.0.0",
    "CONSOLE_PORT": "8100",
    "ALPINE_DIR": "/kk/modules/ui/web/vendor",   # kernel's pinned Alpine.js, in kernel's image
    "COOKIE_PATH": "/console",                    # where the front door serves the console
}
S = {k: os.environ.get(k, v) for k, v in SETTINGS.items()}
ROOT = Path(S["SUBSTRATE_ROOT"])
HERE = Path(__file__).resolve().parent
COOKIE = "substrate_console"
SESSION_HOURS = 8
CSP = ("default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
HEADERS = {"content-security-policy": CSP, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
           "cache-control": "no-store"}

_who: dict[str, tuple[float, dict]] = {}


class Answer:
    def __init__(self, status: int, text: str):
        self.status_code, self.text = status, text

    def json(self):
        return json.loads(self.text)


def _fetch(method: str, url: str, body: dict | None, headers: dict, timeout: float) -> Answer:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={**({"Content-Type": "application/json"} if data else {}), **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return Answer(r.status, r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return Answer(e.code, e.read().decode("utf-8", "replace"))


async def fetch(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None,
                params: dict | None = None, timeout: float = 5.0) -> Answer:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return await asyncio.to_thread(_fetch, method, url, body, headers or {}, timeout)


def j(body, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers=HEADERS)


async def payload(request: Request) -> dict:
    """A POST's JSON body. JSON only: with the SameSite=Strict cookie, this keeps other sites' forms out."""
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise ValueError("JSON only")
    body = await request.json()
    if not isinstance(body, dict):
        raise ValueError("an object")
    return body


# ---------------------------------------------------------------- kernel, with the person's token

async def mcp(token: str, tool: str, **args):
    r = await fetch(S["KERNEL_URL"] + "/mcp", method="POST", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"},
        body={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}},
        timeout=15.0)
    if r.status_code != 200:
        raise PermissionError(f"kernel answered {r.status_code}") if r.status_code in (401, 403) else RuntimeError(r.status_code)
    text = r.text
    if text.startswith("event:") or text.startswith("data:"):   # an SSE answer: the last data line
        text = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")][-1]
    res = json.loads(text)["result"]
    if res.get("isError"):
        raise PermissionError(res["content"][0]["text"])
    sc = res.get("structuredContent")
    return sc.get("result", sc) if sc is not None else json.loads(res["content"][0]["text"])


async def person(request: Request) -> tuple[str, dict] | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    hit = _who.get(token)
    if hit and hit[0] > time.time():
        return token, hit[1]
    try:
        me = await mcp(token, "whoami")
    except Exception:
        return None
    _who[token] = (time.time() + 60, me)
    return token, me


# ---------------------------------------------------------------- the parts, each answered on its own

async def health() -> list[dict]:
    probes = [("kernel", S["KERNEL_URL"] + "/ui/views.json"), ("gateway", S["BIFROST_URL"] + "/health"),
              ("map", S["BACKSTAGE_URL"] + "/.backstage/health/v1/readiness"),
              ("prometheus", S["PROMETHEUS_URL"] + "/-/ready")]
    if S["NOMAD_ADDR"]:
        probes.append(("nomad", S["NOMAD_ADDR"] + "/v1/agent/health"))

    async def one(name, url):
        t = time.monotonic()
        try:
            r = await fetch(url, timeout=3.0)
            return {"name": name, "ok": r.status_code < 400, "ms": round((time.monotonic() - t) * 1000),
                    "detail": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"name": name, "ok": False, "ms": None, "detail": type(e).__name__}

    out = list(await asyncio.gather(*(one(n, u) for n, u in probes)))
    try:
        async with await psycopg.AsyncConnection.connect(S["BUS_URL"], password=S["SUBSTRATE_BUS_PASSWORD"],
                                                         connect_timeout=3) as c:
            await c.execute("select 1")
        out.append({"name": "postgres", "ok": True, "ms": None, "detail": "bus database answers"})
    except Exception as e:
        out.append({"name": "postgres", "ok": False, "ms": None, "detail": type(e).__name__})
    return out


async def prom(query: str) -> list[dict]:
    r = await fetch(S["PROMETHEUS_URL"] + "/api/v1/query", params={"query": query})
    if r.status_code != 200:
        raise RuntimeError(f"Prometheus answered {r.status_code}")
    return r.json()["data"]["result"]


async def spend() -> dict:
    """Bifrost's cost and token counters, through Prometheus (S-05). Prometheus keeps 7 days."""
    try:
        total = await prom("sum(increase(bifrost_cost_total[24h]))")
        tin = await prom("sum(increase(bifrost_input_tokens_total[24h]))")
        tout = await prom("sum(increase(bifrost_output_tokens_total[24h]))")
        by = await prom("sum by (provider) (increase(bifrost_cost_total[24h]))")
        now = int(time.time())
        r = await fetch(S["PROMETHEUS_URL"] + "/api/v1/query_range", params={
            "query": "sum(increase(bifrost_cost_total[1d]))", "start": now - 6 * 86400, "end": now, "step": 86400})
        days = [float(v) for _, v in (r.json()["data"]["result"] or [{"values": []}])[0]["values"]]
        val = lambda res: float(res[0]["value"][1]) if res else 0.0  # noqa: E731
        return {"ok": True, "today": val(total), "tokens_in": val(tin), "tokens_out": val(tout), "days": days,
                "providers": [{"name": x["metric"].get("provider", "all"), "usd": float(x["value"][1])} for x in by]}
    except Exception as e:
        return {"ok": False, "error": f"Prometheus: {type(e).__name__}"}


def _summary(cs: dict) -> dict:
    ops = cs.get("ops") or []
    first = ops[0] if ops else {}
    subj = str(first.get("subject", ""))
    def short(s) -> str:
        s = str(s).rstrip("/")
        if s.startswith("urn:"):
            return ":".join(s.split(":")[-2:])
        return s.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    obj = first.get("object") or {}
    value = obj.get("value") if isinstance(obj, dict) else obj
    value = value if value is not None else (obj.get("entity") if isinstance(obj, dict) else None)
    kind = ("drift" if "discrepancy" in subj else "vocabulary" if first.get("op") in ("add_term", "type")
            else "change")
    return {"id": cs["id"], "kind": kind, "by": cs.get("attributed_to"), "scope": cs.get("target_scope"),
            "at": str(cs.get("submitted_at")), "ops": len(ops),
            "title": " ".join(x for x in [short(subj), short(first.get("predicate", "")), short(value or "")] if x),
            "evidence": (cs.get("validation_report") or {}).get("summary") if isinstance(cs.get("validation_report"), dict) else None}


async def review(token: str) -> dict:
    try:
        rows = await mcp(token, "review_queue", limit=50)
        return {"ok": True, "items": [_summary(cs) for cs in rows]}
    except PermissionError as e:
        return {"ok": False, "error": str(e)[:200]}
    except Exception as e:
        return {"ok": False, "error": f"kernel: {type(e).__name__}"}


def verdicts(limit: int = 8) -> dict:
    """Morphogen's evidence log, newest verdicts first. Copied to a temporary folder so a read-only mount and
    SQLite's WAL files do not get in each other's way."""
    src = ROOT / ".git" / "morphogen" / "evidence.db"
    if not src.exists():
        return {"ok": True, "items": [], "note": "no judged runs yet in this checkout"}
    tmp = Path(tempfile.mkdtemp())
    try:
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(src) + suffix)
            if p.exists():
                shutil.copy(p, tmp / ("evidence.db" + suffix))
        c = sqlite3.connect(tmp / "evidence.db")
        rows = [json.loads(r) for (r,) in c.execute("select raw from evidence order by seq desc limit 500")]
        c.close()
    except Exception as e:
        return {"ok": False, "error": f"evidence log: {type(e).__name__}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = []
    for r in rows:
        if r.get("kind") != "verdict" or r.get("by") != "judge":
            continue
        metrics = (r.get("outcome") or {}).get("metrics") or {}
        gain = next((m.get("gain") for m in metrics.values() if isinstance(m, dict) and "gain" in m), None)
        out.append({"seq": r.get("seq"), "at": r.get("at"), "verdict": r.get("verdict"), "claim": r.get("claim"),
                    "target": (r.get("subject") or {}).get("system"), "cell": r.get("cell"), "gain": gain,
                    "trust": r.get("trust"), "gate": (r.get("gate") or {}).get("decision")})
        if len(out) >= limit:
            break
    return {"ok": True, "items": out}


def _git_head(repo: Path) -> dict:
    g = repo / ".git"
    if not g.is_dir():
        return {"present": False}
    head = (g / "HEAD").read_text().strip()
    branch, sha = None, head
    if head.startswith("ref: "):
        ref = head[5:]
        branch = ref.removeprefix("refs/heads/")
        loose = g / ref
        sha = loose.read_text().strip() if loose.exists() else None
        if sha is None and (g / "packed-refs").exists():
            for line in (g / "packed-refs").read_text().splitlines():
                if line.endswith(" " + ref):
                    sha = line.split()[0]
    heads = g / "refs" / "heads"
    branches = sorted(str(p.relative_to(heads)) for p in heads.rglob("*") if p.is_file()) if heads.exists() else []
    return {"present": True, "branch": branch, "sha": sha, "branches": [b for b in branches if b != "main"]}


def upstream() -> list[dict]:
    try:
        pins = yaml.safe_load((ROOT / "repos.yaml").read_text()) or {}
    except Exception:
        pins = {}
    out = []
    for name in ("kernel", "morphogen"):
        info = _git_head(ROOT / "repos" / name)
        checked = str((pins.get(name) or {}).get("checked", ""))
        patches = sorted(p.name for p in (ROOT / "upstream" / name).glob("*.patch"))
        out.append({"name": name, **info, "checked": checked,
                    "at_checked": bool(info.get("sha") and checked and info["sha"].startswith(checked)),
                    "patches": patches})
    return out


def catalog() -> dict:
    try:
        docs = [d for d in yaml.safe_load_all((ROOT / "catalog-info.yaml").read_text()) if d]
    except Exception as e:
        return {"ok": False, "error": f"catalog-info.yaml: {type(e).__name__}"}
    kinds: dict[str, int] = {}
    for d in docs:
        kinds[d.get("kind", "?")] = kinds.get(d.get("kind", "?"), 0) + 1
    return {"ok": True, "entities": len(docs), "components": kinds.get("Component", 0), "kinds": kinds}


def spec() -> dict:
    """docs/build.yaml: the spec's build plan and where it stands (spec section 10)."""
    path = ROOT / "docs" / "build.yaml"
    if not path.exists():
        return {"present": False}
    try:
        plan = yaml.safe_load(path.read_text()) or {}
    except Exception as e:
        return {"present": True, "error": f"docs/build.yaml: {type(e).__name__}"}
    steps = [{"id": s.get("id"), "title": s.get("title"), "status": s.get("status", "todo"),
              "needs_owner": bool(s.get("needs_owner"))} for s in plan.get("steps", [])]
    nxt = next((s for s in steps if s["status"] not in ("done", "dropped")), None)
    return {"present": True, "steps": steps, "next": nxt}


async def bus() -> dict:
    try:
        async with await psycopg.AsyncConnection.connect(S["BUS_URL"], password=S["SUBSTRATE_BUS_PASSWORD"],
                                                         connect_timeout=3) as c:
            q = await (await c.execute(
                "select queue_name, queue_length, oldest_msg_age_sec, total_messages from pgmq.metrics_all()")).fetchall()
            goals = await (await c.execute(
                "select msg_id, enqueued_at, message from pgmq.q_owner order by msg_id desc limit 5")).fetchall()
        return {"ok": True,
                "queues": [{"name": n, "waiting": w, "oldest_s": a, "total": t} for n, w, a, t in q],
                "proposed": [{"id": i, "at": str(at), **(m if isinstance(m, dict) else {"text": str(m)})}
                             for i, at, m in goals]}
    except Exception as e:
        return {"ok": False, "error": f"bus: {type(e).__name__}"}


# ---------------------------------------------------------------- routes

async def index(request: Request):
    return FileResponse(HERE / "index.html", headers=HEADERS)


async def script(request: Request):
    return FileResponse(HERE / "app.js", media_type="text/javascript", headers=HEADERS)


async def alpine(request: Request):
    # kernel's UI ships Alpine.js; the console uses the same pinned file, served from this origin (CSP: self only)
    found = sorted(Path(S["ALPINE_DIR"]).glob("alpinejs-*.min.js"))
    if not found:
        return Response("Alpine.js not found in kernel's image", status_code=500)
    return FileResponse(found[-1], media_type="text/javascript", headers=HEADERS)


async def login(request: Request):
    try:
        body = await payload(request)
        name, password = str(body["name"]), str(body["password"])
    except Exception:
        return j({"error": "send your kernel name and password"}, 400)
    try:
        r = await fetch(S["KERNEL_URL"] + "/ui/login", method="POST", body={"name": name, "password": password},
                        timeout=15.0)
    except Exception:
        return j({"error": "kernel did not answer; is it up? (scripts/check.sh)"}, 503)
    if r.status_code != 200:
        try:
            msg = r.json().get("error")
        except Exception:
            msg = None
        return j({"error": msg or "name or password not accepted"}, r.status_code if r.status_code < 500 else 502)
    got = r.json()
    resp = j({"role": got["role"]})
    resp.set_cookie(COOKIE, got["token"], max_age=SESSION_HOURS * 3600, httponly=True, samesite="strict",
                    path=S["COOKIE_PATH"])
    return resp


async def logout(request: Request):
    _who.pop(request.cookies.get(COOKIE, ""), None)
    resp = j({"ok": True})
    resp.delete_cookie(COOKIE, path=S["COOKIE_PATH"])
    return resp


async def state(request: Request):
    who = await person(request)
    if not who:
        return j({"error": "sign in"}, 401)
    token, me = who
    services, money, queue, bus_state = await asyncio.gather(health(), spend(), review(token), bus())
    return j({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "me": me,
              "runtime": S["RUNTIME"], "engine": S["CONTAINER_ENGINE"], "services": services, "spend": money,
              "review": queue, "verdicts": verdicts(), "bus": bus_state, "map": catalog(), "upstream": upstream(),
              "spec": spec()})


async def decide(request: Request):
    who = await person(request)
    if not who:
        return j({"error": "sign in"}, 401)
    try:
        body = await payload(request)
        cs, approve = str(body["id"]), bool(body["approve"])
        note = str(body.get("note") or "")[:500] or None
    except Exception:
        return j({"error": "send {id, approve, note}"}, 400)
    try:
        await mcp(who[0], "review", change_set_id=cs, approve=approve, note=note)
    except PermissionError as e:
        return j({"error": str(e)[:300]}, 403)
    except Exception as e:
        return j({"error": f"kernel: {type(e).__name__}"}, 502)
    return j({"ok": True})


async def goal(request: Request):
    who = await person(request)
    if not who:
        return j({"error": "sign in"}, 401)
    try:
        text = str((await payload(request))["text"]).strip()[:500]
    except Exception:
        return j({"error": "send {text}"}, 400)
    if not text:
        return j({"error": "write the goal first"}, 400)
    msg = {"kind": "goal", "text": text, "by": who[1].get("role"),
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        async with await psycopg.AsyncConnection.connect(S["BUS_URL"], password=S["SUBSTRATE_BUS_PASSWORD"],
                                                         connect_timeout=3, autocommit=True) as c:
            row = await (await c.execute("select pgmq.send('owner', %s::jsonb)", (json.dumps(msg),))).fetchone()
    except Exception as e:
        return j({"error": f"bus: {type(e).__name__}"}, 502)
    return j({"ok": True, "id": row[0]})


app = Starlette(routes=[
    Route("/", index), Route("/app.js", script), Route("/vendor/alpine.js", alpine),
    Route("/api/login", login, methods=["POST"]), Route("/api/logout", logout, methods=["POST"]),
    Route("/api/state", state), Route("/api/review", decide, methods=["POST"]),
    Route("/api/goal", goal, methods=["POST"]),
])

if __name__ == "__main__":
    uvicorn.run(app, host=S["CONSOLE_HOST"], port=int(S["CONSOLE_PORT"]), proxy_headers=True,
                forwarded_allow_ips="*", log_level="warning")
