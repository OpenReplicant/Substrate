#!/usr/bin/env python3
"""Spec step 18's trial: model gateways on the same cases (docs/choices/model-gateway.yaml).

Each candidate runs in a container on the stack's network, with its call log in a throwaway database of the
stack's Postgres. Behind it: a fake OpenAI-style model server (fixed usage, so token counts can be checked) and
one real free OpenRouter model (the owner's key, from .env, passed by name and never printed). Output: one line
per candidate and case, and .state/trials/model-gateway/results.jsonl.

    python3 scripts/trials/model-gateway/run.py [bifrost litellm]
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORK = ROOT / ".state/trials/model-gateway"
ENG = os.environ.get("CONTAINER_ENGINE", "podman")
NET = "substrate_default"
DB = "substrate-db-1"

BIFROST_IMAGE = "docker.io/maximhq/bifrost:v2.3.2"
LITELLM_IMAGE = "ghcr.io/berriai/litellm-database:v1.106.4"
PYTHON_IMAGE = "docker.io/library/python:3.13-slim"
REAL_MODEL = "liquid/lfm-2.5-2.6b:free"     # a small free OpenRouter model, from its /api/v1/models on 2026-11-11
MARKER = "zebra-" + secrets.token_hex(6)   # sent in a prompt; must be nowhere in a gateway's store
PORT = {"bifrost": 18090, "litellm": 18091}


def setting(name: str) -> str:
    """A setting through scripts/lib.sh (the secrets slot), never echoed."""
    return subprocess.run(["sh", "-c", '. "$(dirname "$0")/lib.sh"; env_value "$1"', str(ROOT / "scripts/run.sh"), name],
                          capture_output=True, text=True, check=True).stdout.strip()


def sh(*args: str, check: bool = True, env: dict | None = None) -> str:
    r = subprocess.run(args, capture_output=True, text=True, env={**os.environ, **(env or {})})
    if check and r.returncode:
        raise RuntimeError(f"{args[:3]}: {r.stderr.strip()[-400:]}")
    return r.stdout


def psql(db: str, query: str) -> str:
    return sh(ENG, "exec", "-i", DB, "psql", "-U", "postgres", "-d", db, "-At", "-c", query)


def post(url: str, body: dict, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return 0, {"error": str(e)}


def wait_ready(url: str, seconds: int) -> float | None:
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            with urllib.request.urlopen(url, timeout=3):
                return round(time.time() - t0, 1)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return round(time.time() - t0, 1)
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(1)
    return None


def memory_mb(name: str) -> float | None:
    out = sh(ENG, "stats", "--no-stream", "--format", "{{.MemUsage}}", name, check=False).split("/")[0].strip()
    try:
        n, unit = float(out[:-2].strip() if out[-2:].isalpha() else out[:-1]), out[-2:] if out[-2:].isalpha() else out[-1:]
        return round(n * {"kB": 1 / 1024, "MB": 1, "GB": 1024, "B": 1 / 2**20}.get(unit, 1), 0)
    except ValueError:
        return None


def chat(base: str, key: str | None, model: str, text: str, header: str) -> tuple[int, dict]:
    headers = {header: (f"Bearer {key}" if header == "Authorization" else key)} if key else {}
    return post(f"{base}/v1/chat/completions", {"model": model, "messages": [{"role": "user", "content": text}],
                                                 "max_tokens": 200}, headers)


# ---- the fake model server -------------------------------------------------------------------------------------

FAKE = r'''
import json, http.server
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        body = json.dumps({"id": "fake-1", "object": "chat.completion", "created": 1, "model": "fake-small",
                           "choices": [{"index": 0, "message": {"role": "assistant", "content": "pong"}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        body = json.dumps({"object": "list", "data": [{"id": "fake-small", "object": "model"}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
http.server.ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
'''


def start_fake() -> None:
    (WORK / "fake.py").write_text(FAKE)
    sh(ENG, "rm", "-f", "gw-trial-fake", check=False)
    sh(ENG, "run", "-d", "--name", "gw-trial-fake", "--network", NET, "--network-alias", "fake",
       "-v", f"{WORK / 'fake.py'}:/fake.py:ro,Z", PYTHON_IMAGE, "python", "/fake.py")


# ---- candidates ------------------------------------------------------------------------------------------------

def fresh_db(name: str) -> None:
    psql("postgres", f"drop database if exists {name} with (force)")
    psql("postgres", f"create database {name} encoding 'UTF8' template template0")


def bifrost(keys: dict[str, str], pg: str) -> dict:
    """Config from Bifrost v2.3.2's transports/config.schema.json (read 2026-11-11)."""
    db = "gw_trial_bifrost"
    fresh_db(db)
    cfg = {
        "client": {"enable_logging": True, "disable_content_logging": True, "enforce_auth_on_inference": True},
        "source_of_truth": "config.json",
        "providers": {
            "openai": {"keys": [{"name": "fake", "value": "fake-key", "models": ["*"], "weight": 1.0}],
                       "network_config": {"base_url": "http://fake:8000", "allow_private_network": True}},
            "openrouter": {"keys": [{"name": "openrouter", "value": "env.OPENROUTER_API_KEY", "models": ["*"], "weight": 1.0}]},
        },
        "logs_store": {"enabled": True, "type": "postgres",
                       "config": {"host": "db", "port": "5432", "user": "postgres", "password": "env.PGPASSWORD",
                                  "db_name": db, "ssl_mode": "disable"}},
        "governance": {
            "rate_limits": [{"id": "rl-two", "request_max_limit": 2, "request_reset_duration": "1m"}],
            "virtual_keys": [
                {"id": f"vk-{who}", "name": who, "value": key, "is_active": True,
                 **({"rate_limit_id": "rl-two"} if who == "limited" else {}),
                 "provider_configs": [{"provider": "openai", "allowed_models": ["fake-small"], "key_ids": ["*"]},
                                      {"provider": "openrouter", "allowed_models": ["*"], "key_ids": ["*"]}]}
                for who, key in keys.items()]},
    }
    d = WORK / "bifrost"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(cfg, indent=2))
    sh(ENG, "rm", "-f", "gw-trial-bifrost", check=False)
    sh(ENG, "run", "-d", "--name", "gw-trial-bifrost", "--network", NET, "-p", f"127.0.0.1:{PORT['bifrost']}:8080",
       "--tmpfs", "/app/data:rw,mode=1777",   # its image declares a volume there; a trial leaves none behind
       "-e", "APP_HOST=0.0.0.0", "-e", "APP_PORT=8080", "-e", "OPENROUTER_API_KEY", "-e", "PGPASSWORD",
       "-v", f"{d / 'config.json'}:/app/data/config.json:ro,Z", BIFROST_IMAGE, env={"PGPASSWORD": pg})
    return {"name": "gw-trial-bifrost", "db": db, "base": f"http://127.0.0.1:{PORT['bifrost']}",
            "ready": f"http://127.0.0.1:{PORT['bifrost']}/health", "header": "x-bf-vk",
            "fake": "openai/fake-small", "real": f"openrouter/{REAL_MODEL}"}


def bifrost_rows(c: dict, key_ids: dict[str, str]) -> list[dict]:
    q = ("select coalesce(json_agg(json_build_object('model', model, 'prompt', prompt_tokens, 'completion', completion_tokens,"
         " 'latency', latency, 'cost', cost, 'status', status, 'caller', virtual_key_id)), '[]') from logs")
    return json.loads(psql(c["db"], q) or "[]")


def litellm(keys: dict[str, str], pg: str) -> dict:
    """Config from LiteLLM's proxy (v1.106.4): model_list, general_settings (master_key, database_url), litellm_settings."""
    db = "gw_trial_litellm"
    fresh_db(db)
    d = WORK / "litellm"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.yaml").write_text(
        "model_list:\n"
        "  - model_name: fake-small\n"
        "    litellm_params: {model: openai/fake-small, api_base: 'http://fake:8000/v1', api_key: fake-key}\n"
        f"  - model_name: '{REAL_MODEL}'\n"
        f"    litellm_params: {{model: 'openrouter/{REAL_MODEL}', api_key: os.environ/OPENROUTER_API_KEY}}\n"
        "general_settings:\n  master_key: os.environ/LITELLM_MASTER_KEY\n  database_url: os.environ/DATABASE_URL\n"
        "litellm_settings:\n  turn_off_message_logging: true\n")
    master = "sk-" + secrets.token_hex(16)
    sh(ENG, "rm", "-f", "gw-trial-litellm", check=False)
    sh(ENG, "run", "-d", "--name", "gw-trial-litellm", "--network", NET, "-p", f"127.0.0.1:{PORT['litellm']}:4000",
       "-e", "OPENROUTER_API_KEY", "-e", "LITELLM_MASTER_KEY", "-e", "DATABASE_URL",
       "-v", f"{d / 'config.yaml'}:/app/config.yaml:ro,Z", LITELLM_IMAGE, "--config", "/app/config.yaml", "--port", "4000",
       env={"LITELLM_MASTER_KEY": master, "DATABASE_URL": f"postgresql://postgres:{pg}@db:5432/{db}"})
    return {"name": "gw-trial-litellm", "db": db, "base": f"http://127.0.0.1:{PORT['litellm']}",
            "ready": f"http://127.0.0.1:{PORT['litellm']}/health/readiness", "header": "Authorization",
            "fake": "fake-small", "real": REAL_MODEL, "master": master}


def litellm_keys(c: dict, keys: dict[str, str]) -> None:
    for who, key in keys.items():
        body = {"key": key, "key_alias": who, **({"rpm_limit": 2} if who == "limited" else {})}
        code, out = post(f"{c['base']}/key/generate", body, {"Authorization": f"Bearer {c['master']}"})
        if code != 200:
            raise RuntimeError(f"litellm /key/generate {code}: {str(out)[:300]}")


def litellm_rows(c: dict, key_ids: dict[str, str]) -> list[dict]:
    q = ('select coalesce(json_agg(json_build_object(\'model\', model, \'prompt\', prompt_tokens, \'completion\', completion_tokens,'
         ' \'latency\', request_duration_ms, \'cost\', spend, \'status\', status, \'caller\', metadata->>\'user_api_key_alias\')), \'[]\')'
         ' from "LiteLLM_SpendLogs"')
    try:
        return json.loads(psql(c["db"], q) or "[]")
    except RuntimeError:
        return []


# ---- the cases -------------------------------------------------------------------------------------------------

def run(name: str, out) -> None:
    pg = setting("POSTGRES_PASSWORD")
    os.environ["OPENROUTER_API_KEY"] = setting("OPENROUTER_API_KEY")
    keys = {"caller-a": "sk-bf-" + secrets.token_hex(12), "caller-b": "sk-bf-" + secrets.token_hex(12),
            "limited": "sk-bf-" + secrets.token_hex(12)}

    def record(case: str, ok: bool, detail) -> None:
        line = {"candidate": name, "case": case, "pass": bool(ok), "detail": detail}
        out.write(json.dumps(line) + "\n")
        print(f"  {name:8} {case:12} {'pass' if ok else 'FAIL'}  {json.dumps(detail)[:200]}")

    c = (bifrost if name == "bifrost" else litellm)(keys, pg)
    try:
        ready = wait_ready(c["ready"], 180)
        record("ready", ready is not None, {"seconds": ready})
        if ready is None:
            print(sh(ENG, "logs", "--tail", "30", c["name"], check=False)[-2000:])
            return
        if name == "litellm":
            litellm_keys(c, keys)
        code, r = chat(c["base"], keys["caller-a"], c["fake"], f"ping {MARKER}", c["header"])
        text = ((r.get("choices") or [{}])[0].get("message") or {}).get("content")
        record("answer", code == 200 and text == "pong", {"code": code, "text": text, "error": r.get("error") if code != 200 else None})
        code, r = chat(c["base"], keys["caller-b"], c["fake"], f"ping {MARKER}", c["header"])
        record("answer-b", code == 200, {"code": code})
        code, r = chat(c["base"], keys["caller-a"], c["real"], f"Say one word. {MARKER}", c["header"])
        text = ((r.get("choices") or [{}])[0].get("message") or {}).get("content")
        msg = (r.get("choices") or [{}])[0].get("message") or {}
        record("real", code == 200 and bool(text or msg.get("reasoning") or msg.get("reasoning_content")),
               {"code": code, "text": (text or "")[:40], "keys": sorted(msg), "usage": {k: v for k, v in (r.get("usage") or {}).items() if "details" not in k},
                "error": r.get("error") if code != 200 else None})
        code, _ = chat(c["base"], None, c["fake"], "ping", c["header"])
        record("unkeyed", code in (401, 403), {"code": code})
        codes = [chat(c["base"], keys["limited"], c["fake"], "ping", c["header"])[0] for _ in range(3)]
        record("rate", codes[:2] == [200, 200] and codes[2] == 429, {"codes": codes})

        rows = []
        for _ in range(90):   # gateways write their logs in batches (up to three minutes)
            rows = (bifrost_rows if name == "bifrost" else litellm_rows)(c, {})
            if len(rows) >= 5:
                break
            time.sleep(2)
        fake = [x for x in rows if "fake" in (x.get("model") or "")]
        record("record", len(rows) >= 5 and any(x["prompt"] == 7 and x["completion"] == 3 for x in fake)
               and all(x.get("latency") is not None for x in rows),
               {"rows": len(rows), "sample": rows[:2]})
        callers = {x.get("caller") for x in rows}
        record("attribution", len({x for x in callers if x}) >= 2, {"callers": sorted(str(x) for x in callers)})
        dump = sh(ENG, "exec", DB, "pg_dump", "-U", "postgres", "--data-only", c["db"], check=False)
        record("no-content", MARKER not in dump and "pong" not in dump, {"dump_bytes": len(dump), "marker_found": MARKER in dump})
        record("footprint", True, {"memory_mb": memory_mb(c["name"])})
    finally:
        sh(ENG, "rm", "-f", "-v", c["name"], check=False)   # with its anonymous volumes
        psql("postgres", f"drop database if exists {c['db']} with (force)")


def main() -> None:
    names = sys.argv[1:] or ["bifrost", "litellm"]
    WORK.mkdir(parents=True, exist_ok=True)
    for img in (PYTHON_IMAGE, *(BIFROST_IMAGE if n == "bifrost" else LITELLM_IMAGE for n in names)):
        sh(ENG, "pull", "-q", img)
    start_fake()
    try:
        with open(WORK / "results.jsonl", "w") as out:
            for n in names:
                run(n, out)
    finally:
        sh(ENG, "rm", "-f", "gw-trial-fake", check=False)


if __name__ == "__main__":
    main()
