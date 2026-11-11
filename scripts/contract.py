"""Contract tests for substrate's core interfaces (spec section 4, step 9): what any filler of a slot must do, checked
from outside, against the running stack. The map names each test on its API (substrate.dev/contract), and a filler
from the options fills a slot only by passing it. Morphogen's judged runs use morphogen.dev/tests instead: tests of
the code in the tree, which can run in its sandbox (S-87).

    scripts/contract.sh INTERFACE [FILLER]    # e.g. secrets-api openbao; prints each check, exits 0 only on a pass
    scripts/contract.sh all                   # every core interface with its current filler

Each run writes .state/contracts/<interface>--<filler>.json (what was checked, pass or fail, when, on which host),
which substrate:contracts reads into Workbench as claims. Nothing here reads a value it does not need: a secrets
check puts and reads a random probe in a throwaway store, never a real secret.
"""
from __future__ import annotations

import datetime
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("SUBSTRATE_URL", "http://127.0.0.1:8080")
OUT = ROOT / ".state" / "contracts"
CURRENT = {"runtime-api": "compose", "secrets-api": "env", "workbench-api": "postgrest", "workbench-mcp-api": "workbench-server",
           "workbench-server-api": "workbench-server", "graph-api": "ontop", "judge-api": "morphogen",
           "database-api": "postgres", "tools-api": "substrate-tools", "sandbox-api": "podman", "repository-api": "git",
           "evidence-api": "morphogen-evidence", "model-api": "bifrost",
           "embedding-api": "qwen3-embedding-0.6b"}


class Run:
    def __init__(self, interface: str, filler: str):
        self.interface, self.filler, self.checks = interface, filler, []

    def check(self, name: str, ok, detail="") -> bool:
        ok = bool(ok)
        self.checks.append({"name": name, "ok": ok, "detail": "" if ok else str(detail)[:300]})
        print(("  ok    " if ok else "  FAIL  ") + name + ("" if ok else f": {str(detail)[:200]}"))
        return ok


def sh(script: str, env: dict | None = None, stdin: str | None = None, timeout: int = 120) -> tuple[int, str]:
    """A shell snippet with scripts/lib.sh loaded (and so the runtime's and the secrets slot's verbs)."""
    p = subprocess.run(["sh", "-c", '. "$(dirname "$0")/lib.sh"; ' + script, str(ROOT / "scripts" / "contract.sh")],
                       env={**os.environ, **(env or {})}, input=stdin, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout if p.returncode == 0 else p.stdout + p.stderr)


def got(script: str, env: dict) -> tuple[int, str]:
    """What a caller sees: $(...) of the snippet, its trailing newlines dropped as the shell drops them."""
    code, out = sh(script, env)
    return code, out.rstrip("\n")


def http(method: str, path: str, body=None, headers: dict | None = None, form: dict | None = None) -> tuple[int, str]:
    data = None
    h = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


def js(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return None


def token() -> dict:
    p = subprocess.run([str(ROOT / "scripts" / "workbench-mcp-headers.sh")], capture_output=True, text=True, timeout=60)
    return json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip().startswith("{") else {}


# ------------------------------------------------------------------ runtime-api: rt_up, rt_down, rt_status, rt_logs
def runtime(r: Run):
    env = {"RUNTIME": r.filler}
    code, out = sh("for v in rt_up rt_down rt_status rt_logs; do command -v $v >/dev/null || echo missing $v; done", env)
    r.check(f"scripts/runtime/{r.filler}.sh defines the four verbs", code == 0 and "missing" not in out, out)
    import yaml
    services = sorted((yaml.safe_load((ROOT / "deploy/compose.yaml").read_text()).get("services") or {}))
    code, out = sh("rt_status", env)
    r.check("rt_status answers", code == 0, out)
    missing = [s for s in services if f"-{s}-" not in out and f" {s} " not in f" {out} "]
    r.check("rt_status names every service the stack declares", not missing, f"not listed: {missing}")
    code, out = sh(f"rt_logs {services[0]}", env)
    r.check("rt_logs SERVICE answers with its lines", code == 0 and out.strip(), out[-200:])
    code, out = sh("rt_logs no-such-service-here", env)
    r.check("rt_logs of a service the stack lacks fails", code != 0, out[-200:])


# ------------------------------------------------------------------ secrets-api: sec_* verbs, env_value
def secrets_api(r: Run):
    work = Path(tempfile.mkdtemp(prefix="secrets-", dir=OUT))
    env = {"SECRETS": r.filler, "SUBSTRATE_ENV_FILE": str(work / "env"), "BAO_DIR": str(work / "openbao"),
           "BAO_NAME": "substrate-openbao-contract"}
    (work / "env").write_text(f"SECRETS={r.filler}\n")
    os.chmod(work / "env", 0o600)
    try:
        code, out = sh("for v in sec_start sec_stop sec_get sec_put sec_status; do command -v $v >/dev/null || echo missing $v; done", env)
        r.check(f"scripts/secrets/{r.filler}.sh defines the five verbs", code == 0 and "missing" not in out, out)
        code, out = sh("sec_start", env, timeout=180)
        r.check("sec_start brings the store up", code == 0, out)
        code, out = sh("sec_status", env)
        r.check("sec_status answers", code == 0 and out.strip(), out)
        name = "SUBSTRATE_CONTRACT_PROBE"
        value = f"{secrets.token_urlsafe(24)} with spaces = and-dashes_{secrets.token_hex(4)}"
        code, out = sh(f"sec_put {name}", env, stdin=value + "\n")
        r.check("sec_put takes a value on stdin", code == 0, out)
        code, out = got(f"sec_get {name}", env)
        r.check("$(sec_get NAME) is exactly what was put (URL-safe characters, spaces, =)", code == 0 and out == value, "a different value came back")
        second = secrets.token_urlsafe(32)
        sh(f"sec_put {name}", env, stdin=second)
        code, out = got(f"sec_get {name}", env)
        r.check("sec_put again replaces the value", code == 0 and out == second, "the old value came back")
        code, out = got("sec_get SUBSTRATE_CONTRACT_NEVER_SET", env)
        r.check("an unset name reads as empty", code == 0 and out == "", "non-empty or failed")
        code, out = got(f'export SECRETS={r.filler}; is_secret() {{ [ "$1" = {name} ]; }}; env_value {name}', env)
        r.check("env_value reads a secret through the slot", code == 0 and out == second, "a different value came back")
        mode = (work / "env").stat().st_mode & 0o777
        r.check("the store's files are private to their owner", mode == 0o600 and not any(
            p.stat().st_mode & 0o077 for p in (work / "openbao" / "keys").glob("*")) if (work / "openbao" / "keys").is_dir() else mode == 0o600,
            f"mode {oct(mode)}")
    finally:
        sh("sec_stop", env)
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------ workbench-api: PostgREST over the api schema
def workbench_api(r: Run):
    code, out = http("GET", "/api/")
    doc = js(out) or {}
    r.check("GET /api/ is an OpenAPI 2.0 description", code == 200 and doc.get("swagger") == "2.0" and doc.get("paths"), code)
    code, out = http("GET", "/api/claims?limit=1")
    r.check("without a token, nothing but sign-in is readable", code in (401, 403), f"{code} {out[:100]}")
    code, out = http("POST", "/api/rpc/login", {"name": "no-such-person", "pass": "wrong"})
    r.check("a wrong name or password is refused", code in (400, 401, 403), code)
    h = token()
    code, out = http("GET", "/api/rpc/whoami", headers=h)
    r.check("with a token, rpc/whoami names the caller", code == 200 and (js(out) or {}).get("name"), out[:100])
    code, out = http("GET", "/api/content_types?select=id", headers=h)
    r.check("content_types lists the types", code == 200 and isinstance(js(out), list) and js(out), out[:100])
    t = (js(out) or [{}])[0].get("id")
    code, out = http("GET", f"/api/{t}?limit=1", headers=h)
    r.check("each type is served at /api/<type>", code == 200 and isinstance(js(out), list), out[:100])
    code, out = http("GET", "/api/claims?limit=1&select=field,author,status,quote", headers=h)
    r.check("claims are served beside the items", code == 200 and isinstance(js(out), list), out[:100])


# ------------------------------------------------------------------ workbench-mcp-api: MCP over HTTP
def workbench_mcp(r: Run):
    rpc = lambda m, p=None, h=None: http("POST", "/wb/api/mcp", {"jsonrpc": "2.0", "id": 1, "method": m, "params": p or {}},  # noqa: E731
                                          headers={"Accept": "application/json", **(h or {})})
    code, out = rpc("tools/list")
    r.check("without a token, MCP answers 401 so a client can fetch one", code == 401, code)
    h = token()
    code, out = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "contract", "version": "1"}}, h)
    r.check("initialize names the server", code == 200 and ((js(out) or {}).get("result") or {}).get("serverInfo"), out[:150])
    code, out = rpc("tools/list", None, h)
    names = {t["name"] for t in ((js(out) or {}).get("result") or {}).get("tools") or []}
    want = {"search", "get_item", "save_item", "claims", "list_types", "list_items", "open_decisions", "decide"}
    r.check("tools/list offers search, items, claims, types and decisions", want <= names, f"missing {sorted(want - names)}")
    code, out = rpc("tools/call", {"name": "list_types", "arguments": {}}, h)
    res = (js(out) or {}).get("result") or {}
    r.check("a tool call answers with content", code == 200 and res.get("content") and not res.get("isError"), out[:150])


# ------------------------------------------------------------------ workbench-server-api: /wb/api
def workbench_server(r: Run):
    code, out = http("GET", "/wb/api/openapi.json")
    paths = set(((js(out) or {}).get("paths") or {}))
    want = {"/wb/api/health", "/wb/api/events", "/wb/api/extractors", "/wb/api/extract", "/wb/api/mcp"}
    r.check("its OpenAPI 3 document lists health, events, extractors, extract and mcp",
            code == 200 and str((js(out) or {}).get("openapi", "")).startswith("3.") and want <= paths, f"missing {sorted(want - paths)}")
    code, out = http("GET", "/wb/api/health")
    r.check("health answers ok", code == 200 and (js(out) or {}).get("ok") is True, out[:100])
    code, _ = http("GET", "/wb/api/extractors")
    r.check("extractors asks for a token", code == 401, code)
    code, _ = http("POST", "/wb/api/extract", {"extractor": "none:none"})
    r.check("queueing a run asks for a token", code == 401, code)
    code, out = http("GET", "/wb/api/extractors", headers=token())
    r.check("with a token, extractors lists each with its key", code == 200 and all("key" in x for x in js(out) or [{}]) and js(out), out[:100])


# ------------------------------------------------------------------ graph-api: SPARQL 1.1, read-only, reasoning
def graph_api(r: Run):
    q = lambda text: http("POST", "/sparql", form={"query": text}, headers={"Accept": "application/sparql-results+json"})  # noqa: E731
    code, out = q("ASK {}")
    r.check("answers the SPARQL 1.1 protocol", code == 200 and (js(out) or {}).get("boolean") is True, out[:100])
    wb = "PREFIX wb: <https://workbench.local/ns#> "
    code, out = q(wb + "SELECT (COUNT(?x) AS ?n) WHERE { ?x a wb:Item }")
    n = int((((js(out) or {}).get("results") or {}).get("bindings") or [{}])[0].get("n", {}).get("value", 0))
    r.check("reasons over classes: every item is a wb:Item, though none is typed so directly", code == 200 and n > 0, out[:150])
    code, out = q(wb + "SELECT (COUNT(*) AS ?n) WHERE { ?a wb:relatedTo ?b }")
    n = int((((js(out) or {}).get("results") or {}).get("bindings") or [{}])[0].get("n", {}).get("value", 0))
    r.check("reasons over properties: every relation is a wb:relatedTo", code == 200 and n > 0, out[:150])
    code, out = q(wb + "SELECT ?q WHERE { ?c a wb:Claim ; wb:quote ?q } LIMIT 1")
    r.check("claims are queryable with their quotes", code == 200 and (((js(out) or {}).get("results") or {}).get("bindings")), out[:150])
    code, out = http("POST", "/sparql", form={"update": "INSERT DATA { <urn:x> <urn:y> <urn:z> }"})
    r.check("an update is refused (read-only)", code >= 400 or code == 0, f"{code} {out[:100]}")


# ------------------------------------------------------------------ judge-api: Morphogen, from outside only
def judge_api(r: Run):
    mg = [str(ROOT / "bin" / "morphogen")]
    p = subprocess.run(mg + ["status"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    d = js(p.stdout) or {}
    r.check("status reports the project and its cells", p.returncode == 0 and d.get("project") and d.get("cells"), p.stderr[-200:])
    p = subprocess.run(mg + ["structure", "check", "morphogen.yaml"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    d = js(p.stdout) or {}
    errors = [f for f in d.get("findings") or [] if f.get("severity") == "error"]
    r.check("structure check reads the map with no errors", p.returncode == 0 and "findings" in d and not errors, errors or p.stderr[-200:])
    p = subprocess.run(mg + ["evidence", "--verify"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    r.check("its evidence log's chain verifies", p.returncode == 0 and (js(p.stdout) or {}).get("chain") == "intact", p.stdout[-200:])


# ------------------------------------------------------------------ what core parts rely on beneath the slots
def database_api(r: Run):
    """Postgres as the stack needs it: version 17, the extensions Workbench and pgGraph use, Workbench's roles."""
    code, out = sh('$ENGINE exec "$(compose ps -q db)" psql -U postgres -d workbench -Atc '
                   '"select current_setting(\'server_version_num\'), string_agg(extname, \',\' order by extname) from pg_extension"', {})
    ver, _, ext = out.strip().partition("|")
    r.check("Postgres 17 answers", code == 0 and ver.startswith("17"), out[-200:])
    r.check("the extensions Workbench uses are created: pgmq (jobs), pgGraph (paths)", {"pgmq", "graph"} <= set(ext.split(",")), f"have {ext}")
    code, out = sh('$ENGINE exec "$(compose ps -q db)" psql -U postgres -d workbench -Atc '
                   '"select string_agg(name, \',\' order by name) from pg_available_extensions"', {})
    need = {"vector", "pg_cron", "pgmq", "graph"}
    r.check("pgvector, pg_cron, pgmq and pgGraph are available to create", need <= set(out.strip().split(",")), f"missing {sorted(need - set(out.strip().split(',')))}")
    code, out = sh('$ENGINE exec "$(compose ps -q db)" psql -U postgres -d workbench -Atc '
                   '"select string_agg(rolname, \',\' order by rolname) from pg_roles where rolname like \'wb_%\'"', {})
    need = {"wb_anon", "wb_viewer", "wb_editor", "wb_owner", "wb_authenticator", "wb_server", "wb_reader"}
    r.check("Workbench's roles exist", need <= set(out.strip().split(",")), f"have {out.strip()}")


def tools_api(r: Run):
    """The tools container runs what bin/ wraps, as the user, with the checkout mounted."""
    for name, cmd in (("bin/in-tools runs a command in the tools container", [str(ROOT / "bin/in-tools"), "true"]),
                      ("bin/gitleaks answers", [str(ROOT / "bin/gitleaks"), "version"]),
                      ("bin/morphogen answers", [str(ROOT / "bin/morphogen"), "--help"])):
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
        r.check(name, p.returncode == 0, (p.stderr or p.stdout)[-200:])
    p = subprocess.run([str(ROOT / "bin/in-tools"), "sh", "-c", f"test -f {ROOT}/catalog-info.yaml && id -u"], capture_output=True, text=True, timeout=120)
    r.check("it sees this checkout, as this user", p.returncode == 0 and p.stdout.strip() == str(os.getuid()), (p.stderr or p.stdout)[-200:])


def sandbox_api(r: Run):
    """The engine starts a container with no network, a read-only root and no capabilities, and it cannot reach out."""
    _, engine = sh('printf %s "$ENGINE"', {})
    probe = ("import socket, sys\n"
             "try:\n    open('/x', 'w'); print('writable')\nexcept OSError: pass\n"
             "try:\n    socket.create_connection(('1.1.1.1', 53), 2); print('online')\nexcept OSError: pass\n"
             "print('done')\n")
    p = subprocess.run([engine, "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                        "--security-opt", "no-new-privileges", "localhost/substrate-tools:local", "python3", "-c", probe],
                       capture_output=True, text=True, timeout=120)
    out = p.stdout + p.stderr
    r.check("the engine runs a locked-down container", p.returncode == 0 and "done" in out, out[-200:])
    r.check("its root filesystem is read-only", "writable" not in out, out[-200:])
    r.check("it has no network", "online" not in out, out[-200:])


def repository_api(r: Run):
    """A git repository Morphogen can judge in: a resolvable HEAD, history, and its own git directory."""
    run = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=60)  # noqa: E731
    p = run("rev-parse", "--verify", "HEAD")
    r.check("HEAD resolves to a commit", p.returncode == 0 and len(p.stdout.strip()) == 40, p.stderr[-200:])
    p = run("rev-list", "--count", "HEAD")
    r.check("it has history", p.returncode == 0 and int(p.stdout.strip() or 0) > 1, p.stderr[-200:])
    p = run("rev-parse", "--git-common-dir")
    r.check("its git directory is found", p.returncode == 0 and (ROOT / p.stdout.strip()).is_dir(), p.stderr[-200:])


def evidence_api(r: Run):
    """Morphogen's evidence log: its hash chain verifies, read by Morphogen and, independently, by substrate:morphogen."""
    p = subprocess.run([str(ROOT / "bin/morphogen"), "evidence", "--verify"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    d = js(p.stdout) or {}
    r.check("Morphogen verifies the chain", p.returncode == 0 and d.get("chain") == "intact", p.stdout[-200:])
    sys.path.insert(0, str(ROOT / "plugins/substrate"))
    import substrate_plugin as sp
    log = Path(d.get("path") or sp.git_common_dir(ROOT) / "morphogen" / "evidence.db")
    try:
        n = len(sp.read_evidence(log)) if log.is_file() else 0
        r.check("an independent reader verifies the same chain", n == d.get("records", 0), f"{n} against {d.get('records')}")
    except sp.ChainBroken as e:
        r.check("an independent reader verifies the same chain", False, e)


def model_api(r: Run):
    """The model gateway (S-77): one OpenAI-style endpoint; a call needs a caller's key; only allowed models; every
    call kept in the gateway's own record with its caller and the call id it carried, without its content; the
    record readable, not writable, by the meter's login."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import gateway as g
    env = g.settings()
    port = sh("env_value GATEWAY_PORT")[1].strip() or "8090"
    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    callers = g.callers()
    r.check("the map's model handlers each have a caller (streams.yaml)", any(c.startswith("handler:") for c in callers), callers)
    caller = "contract:model-api"         # its own key and budget, so the test never spends a handler's
    cfg = json.loads((ROOT / ".state/gateway/config.json").read_text()) if (ROOT / ".state/gateway/config.json").is_file() else {}
    limits = [k.get("rate_limit_id") for k in (cfg.get("governance") or {}).get("virtual_keys", []) if k.get("rate_limit_id")]
    r.check("each capped caller has a limit of its own (a shared limit is one shared counter)", limits and len(limits) == len(set(limits)), limits)
    key = g.caller_key(env["GATEWAY_KEY_SECRET"], caller)
    marker = "probe-" + secrets.token_hex(6)

    def call(model, key, cid):
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": f"Say ok. {marker}"}], "max_tokens": 20}).encode()
        headers = {"Content-Type": "application/json", "x-wb-call": cid, **({"x-bf-vk": key} if key else {})}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=120) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, js(e.read().decode(errors="replace")) or {}

    ids = {k: f"contract-{k}-{secrets.token_hex(4)}" for k in ("unkeyed", "stranger", "paid", "free")}
    code, _ = call("openrouter/google/gemma-4-26b-a4b-it:free", None, ids["unkeyed"])
    r.check("a call without a key is refused", code == 401, code)
    code, _ = call("openrouter/google/gemma-4-26b-a4b-it:free", "sk-bf-" + secrets.token_hex(20), ids["stranger"])
    r.check("a key the gateway did not issue is refused", code in (401, 403), code)
    code, out = call("openrouter/openai/gpt-4o", key, ids["paid"])
    r.check("a model outside the allowed ones (free only, by default) is refused", code in (400, 403), (code, str(out)[:160]))
    code, out = call("openrouter/google/gemma-4-26b-a4b-it:free", key, ids["free"])
    upstream = code == 429 and "upstream" in json.dumps(out).lower()
    r.check("an allowed model answers through it (or its provider's own rate limit comes back as such)", code == 200 or upstream, (code, str(out)[:160]))

    seen = {"rows": {}, "writable": None}
    for _ in range(15):     # the gateway writes its log in batches
        p = subprocess.run([str(ROOT / "bin/in-tools"), "python3", str(ROOT / "scripts/gateway.py"), "meter", *ids.values()],
                           capture_output=True, text=True, timeout=60)
        seen = js(p.stdout) or seen
        if ids["free"] in seen["rows"] and ids["paid"] in seen["rows"]:
            break
        time.sleep(2)
    rows = seen["rows"]
    r.check("the gateway keeps its own record of each keyed call, with the call id it carried",
            ids["free"] in rows and ids["paid"] in rows, sorted(rows) or p.stderr[-200:])
    r.check("the record says whose call it was", rows and all(rows[i]["caller"] == caller for i in (ids["free"], ids["paid"]) if i in rows),
            {k: v["caller"] for k, v in rows.items()})
    r.check("the record has the call's time", (rows.get(ids["free"]) or {}).get("latency") is not None, rows.get(ids["free"]))
    r.check("no prompt or answer is kept", rows and not any(marker in v["content"] for v in rows.values()), "the probe's text is in the log")
    wrote = seen["writable"] is not False
    r.check("the meter's login can read the record and not change it", not wrote, "gateway_meter may delete from logs")


def embedding_api(r: Run):
    """Recall's embeddings (S-83): an OpenAI-style /v1/embeddings at the gateway, under Workbench's own key, which
    reaches local models only; the same text gives the same vector, of one fixed size; meaning is in it (a
    synonym is nearer than an unrelated word); and recall through the API uses it."""
    env = {k: sh(f"env_value {k}")[1].strip() for k in ("GATEWAY_PORT", "WORKBENCH_EMBED_KEY", "WORKBENCH_EMBED_MODEL")}
    model, key = env["WORKBENCH_EMBED_MODEL"], env["WORKBENCH_EMBED_KEY"]
    r.check("an embedding model is set", model, "WORKBENCH_EMBED_MODEL is empty")
    url = f"http://127.0.0.1:{env['GATEWAY_PORT'] or 8090}"

    def post(path, body, key):
        req = urllib.request.Request(url + path, json.dumps(body).encode(),
                                     {"Content-Type": "application/json", **({"x-bf-vk": key} if key else {})})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, js(e.read().decode(errors="replace")) or {}

    code, _ = post("/v1/embeddings", {"model": model, "input": ["x"]}, None)
    r.check("an embedding without a key is refused", code == 401, code)
    code, _ = post("/v1/chat/completions", {"model": "openrouter/google/gemma-4-31b-it:free",
                                             "messages": [{"role": "user", "content": "hi"}]}, key)
    r.check("Workbench's key cannot reach a model off this machine", code == 403, code)
    words = ["a car needs new tyres", "the automobile needs new tyres", "send the invoice by Friday", "a car needs new tyres"]
    code, out = post("/v1/embeddings", {"model": model, "input": words}, key)
    vs = [d["embedding"] for d in sorted(out.get("data") or [], key=lambda d: d["index"])]
    r.check("the endpoint embeds through the gateway", code == 200 and len(vs) == 4, (code, str(out)[:160]))
    if len(vs) == 4:
        cos = lambda a, b: sum(x * y for x, y in zip(a, b)) / ((sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5))  # noqa: E731
        r.check("one size for every vector", len({len(v) for v in vs}) == 1, {len(v) for v in vs})
        r.check("the same text gives the same vector", cos(vs[0], vs[3]) > 0.999, cos(vs[0], vs[3]))
        r.check("meaning is in it: a synonym is nearer than an unrelated text", cos(vs[0], vs[1]) > cos(vs[0], vs[2]),
                (cos(vs[0], vs[1]), cos(vs[0], vs[2])))
    code, out = got("scripts/workbench.sh recall 'where are model calls counted'", {})
    hits = js(out) or []
    r.check("recall uses it: meaning finds items, beside words and the graph",
            any("vector" in (h.get("via") or "") for h in hits), out[-200:])


TESTS = {"runtime-api": runtime, "secrets-api": secrets_api, "workbench-api": workbench_api, "workbench-mcp-api": workbench_mcp,
         "workbench-server-api": workbench_server, "graph-api": graph_api, "judge-api": judge_api,
         "database-api": database_api, "tools-api": tools_api, "sandbox-api": sandbox_api, "repository-api": repository_api,
         "evidence-api": evidence_api, "model-api": model_api,
         "embedding-api": embedding_api}


def one(interface: str, filler: str) -> bool:
    print(f"== {interface} ({filler})")
    r = Run(interface, filler)
    try:
        TESTS[interface](r)
    except Exception as e:                        # a filler that crashes the test fails it
        r.check("the test ran to the end", False, f"{type(e).__name__}: {e}")
    passed = bool(r.checks) and all(c["ok"] for c in r.checks)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{interface}--{filler}.json").write_text(json.dumps({
        "interface": interface, "filler": filler, "passed": passed, "checks": r.checks, "host": socket.gethostname(),
        "ran_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "command": f"scripts/contract.sh {interface} {filler}"}, indent=1) + "\n")
    print(f"  {'passes' if passed else 'FAILS'}: {sum(c['ok'] for c in r.checks)}/{len(r.checks)}")
    return passed


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in (*TESTS, "all"):
        print(__doc__)
        print("interfaces:", ", ".join(TESTS))
        return 2
    if argv[0] == "all":
        return 0 if all([one(i, f) for i, f in CURRENT.items()]) else 1
    return 0 if one(argv[0], argv[1] if len(argv) > 1 else CURRENT[argv[0]]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
