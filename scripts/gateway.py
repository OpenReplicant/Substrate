#!/usr/bin/env python3
"""The model gateway (spec step 18, S-77): Bifrost's config.json rendered from .env and streams.yaml.

    python3 scripts/gateway.py render     # writes .state/gateway/config.json (no secret in it: Bifrost reads env.NAME)
    python3 scripts/gateway.py keys       # the callers that get a key (each model handler in streams.yaml)
    bin/in-tools python3 scripts/gateway.py init   # its database and logins, in the tools container (up.sh runs it)
    bin/in-tools python3 scripts/gateway.py meter CALL_ID...   # what the meter's login sees of these calls (the contract test)
    bin/in-tools python3 scripts/gateway.py judge-meter open|close RUN_ID   # Morphogen's meter for judged runs (S-87)

Providers are the ones this machine has: OpenRouter when OPENROUTER_API_KEY is set (free models only, unless
GATEWAY_OPENROUTER_MODELS says otherwise), Ollama when OLLAMA_URL is set. Every call is logged by the gateway in its
own database (`gateway` on the stack's Postgres) without message content; a call with no key is refused; each
caller has its own virtual key, rate-limited, derived from GATEWAY_KEY_SECRET so the handlers plugin reaches the
same key without it being stored (plugins/handlers/README.md, "Model handlers"). Keys and fields from Bifrost
v2.3.2's transports/config.schema.json (read 2026-11-11).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".state/gateway/config.json"


NAMES = ("POSTGRES_PASSWORD", "DB_PORT", "OPENROUTER_API_KEY", "OLLAMA_URL", "GATEWAY_OPENROUTER_MODELS",
         "GATEWAY_REQUESTS_PER_HOUR", "GATEWAY_DB_PASSWORD", "GATEWAY_METER_PASSWORD", "GATEWAY_KEY_SECRET",
         "GATEWAY_PORT", "WORKBENCH_EMBED_MODEL")


def settings() -> dict[str, str]:
    """The settings this needs, each through scripts/lib.sh's env_value (the secrets slot, S-31); kept in memory."""
    out = subprocess.run(["sh", "-c", '. "$(dirname "$0")/lib.sh"; for n in "$@"; do printf "%s=" "$n"; env_value "$n" | base64 -w0; echo; done',
                          str(ROOT / "scripts/gateway.sh"), *NAMES], capture_output=True, text=True, check=True).stdout
    return {k: base64.b64decode(v).decode().strip() for k, _, v in (l.partition("=") for l in out.splitlines()) if k}


def caller_key(secret: str, caller: str) -> str:
    """The virtual key a caller gets: the same formula as the handlers plugin's (handlers_plugin.caller_key)."""
    return "sk-bf-" + hmac.new(secret.encode(), caller.encode(), hashlib.sha256).hexdigest()[:40]


# Callers that are not handlers, and the only providers each may use (S-83): Workbench's embeddings stay local.
FIXED = {"workbench:embed": ("ollama",), "contract:model-api": ("openrouter", "ollama"),
         # Morphogen's judged runs (S-87): the one key a judged run is given, by the meter below; local models only,
         # so a verdict's hundred-odd calls spend no provider's quota and need no hourly cap
         "judge:morphogen": ("ollama",)}
JUDGE = "judge:morphogen"
LOCAL = ("ollama",)
FIXED_KEYS = {"workbench:embed": "WORKBENCH_EMBED_KEY"}   # read from .env by the gateway, the server and the tools


def callers() -> list[str]:
    spec = yaml.safe_load((ROOT / "streams.yaml").read_text()) or {}
    return sorted(f"handler:{h}" for s in (spec.get("streams") or {}).values()
                  for h, d in (s.get("handlers") or {}).items() if (d or {}).get("kind") == "model") + sorted(FIXED)


def pg(env: dict, db: str = "gateway") -> dict:
    return {"host": "db", "port": "5432", "user": "gateway", "password": "env.GATEWAY_DB_PASSWORD", "db_name": db, "ssl_mode": "disable"}


def render(env: dict[str, str]) -> dict:
    providers: dict[str, dict] = {}
    if env.get("OPENROUTER_API_KEY"):
        providers["openrouter"] = {"keys": [{"name": "openrouter", "value": "env.OPENROUTER_API_KEY", "models": ["*"], "weight": 1.0}]}
    if env.get("OLLAMA_URL"):
        providers["ollama"] = {"keys": [{"name": "ollama", "value": "", "models": ["*"], "weight": 1.0,
                                         "ollama_key_config": {"url": env["OLLAMA_URL"]}}],
                               "network_config": {"base_url": env["OLLAMA_URL"], "allow_private_network": True}}
    allowed = {"openrouter": [m.strip() for m in (env.get("GATEWAY_OPENROUTER_MODELS") or "regex:.*:free").split(",") if m.strip()],
               "ollama": ["regex:.*"]}
    secret = env.get("GATEWAY_KEY_SECRET") or ""
    per_hour = int(env.get("GATEWAY_REQUESTS_PER_HOUR") or 120)
    return {
        "source_of_truth": "config.json",
        # every call logged, without its content; a call needs a key; the call id a caller sends is kept with it
        "client": {"enable_logging": True, "disable_content_logging": True, "enforce_auth_on_inference": True,
                   "logging_headers": ["x-wb-call"], "log_retention_days": 365},
        "providers": providers,
        "config_store": {"enabled": True, "type": "postgres", "config": pg(env)},
        "logs_store": {"enabled": True, "type": "postgres", "config": pg(env)},
        "governance": {
            "auth_config": {"is_enabled": True, "admin_username": "admin", "admin_password": "env.GATEWAY_ADMIN_PASSWORD"},
            # one limit per caller: a limit several keys point at is one counter, shared (seen 2026-11-11, S-83)
            "rate_limits": [{"id": "rl-" + c.replace(":", "-"), "request_max_limit": per_hour, "request_reset_duration": "1h"}
                            for c in callers() if not set(FIXED.get(c, providers)) <= set(LOCAL)] if secret else [],
            "virtual_keys": [{
                "id": "vk-" + c.replace(":", "-"), "name": c, "is_active": True,
                "value": f"env.{FIXED_KEYS[c]}" if c in FIXED_KEYS else caller_key(secret, c),
                "description": f"{c}'s calls, counted by the gateway",
                # the hourly cap guards a provider's quota; a caller held to local models has none to guard
                **({} if set(FIXED.get(c, providers)) <= set(LOCAL) else {"rate_limit_id": "rl-" + c.replace(":", "-")}),
                "provider_configs": [{"provider": p, "allowed_models": allowed[p], "key_ids": ["*"]} for p in providers
                                     if p in FIXED.get(c, providers)],
            } for c in callers()] if secret else [],
        },
    }


def init(env: dict[str, str]) -> None:
    """The gateway's database and its two logins, made once and kept: `gateway` owns the database (Bifrost makes
    its tables there), `gateway_meter` may only read them (the handlers plugin's meter)."""
    import psycopg
    from psycopg import sql
    admin = f"postgresql://postgres:{env['POSTGRES_PASSWORD']}@127.0.0.1:{env.get('DB_PORT') or 5432}"
    with psycopg.connect(admin + "/postgres", autocommit=True) as c:
        for role, pw in (("gateway", env["GATEWAY_DB_PASSWORD"]), ("gateway_meter", env["GATEWAY_METER_PASSWORD"])):
            if not c.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone():
                c.execute(sql.SQL("create role {} login").format(sql.Identifier(role)))
            c.execute(sql.SQL("alter role {} password {}").format(sql.Identifier(role), sql.Literal(pw)))
        if not c.execute("select 1 from pg_database where datname = 'gateway'").fetchone():
            c.execute("create database gateway owner gateway encoding 'UTF8' template template0")
        c.execute("revoke all on database gateway from public")
        c.execute("grant connect on database gateway to gateway_meter")
    with psycopg.connect(admin + "/gateway", autocommit=True) as c:
        c.execute("grant usage on schema public to gateway_meter")
        c.execute("grant select on all tables in schema public to gateway_meter")
        c.execute("alter default privileges for role gateway in schema public grant select on tables to gateway_meter")
    print("  gateway database and logins (gateway, gateway_meter): ready")


def meter(env: dict[str, str], ids: list[str]) -> dict:
    """What the meter's login sees of these call ids (each row's caller, status, latency, and whether any content
    was kept), and whether that login can change the record. In the tools container: it needs psycopg."""
    import psycopg
    url = f"postgresql://gateway_meter:{env['GATEWAY_METER_PASSWORD']}@127.0.0.1:{env.get('DB_PORT') or 5432}/gateway"
    with psycopg.connect(url, connect_timeout=5) as c:
        rows = c.execute("""select metadata::jsonb->>'x-wb-call', virtual_key_name, status, latency,
                                   concat_ws(' ', input_history, output_message, content_summary, raw_request, raw_response)
                              from logs where metadata::jsonb->>'x-wb-call' = any(%s)""", (ids,)).fetchall()
    with psycopg.connect(url, connect_timeout=5) as c:
        try:
            c.execute("delete from logs where false")
            writable = True
        except psycopg.Error:
            writable = False
    return {"rows": {r[0]: {"caller": r[1], "status": r[2], "latency": float(r[3]) if r[3] is not None else None, "content": r[4] or ""}
                     for r in rows}, "writable": writable}


def judge_meter(env: dict[str, str], op: str, run_id: str) -> dict:
    """Morphogen's meter for a judged run (its PLAN.md 7c; morphogen.local.yaml's gateway.meter):
    `open RUN_ID` gives the run the judge's key, the only one it holds; `close RUN_ID` counts, from the gateway's
    own record, every call made with that key since the run opened (runs are judged one at a time). In the tools
    container: it needs psycopg."""
    state = ROOT / ".state/gateway/judge"
    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", run_id):
        raise SystemExit(f"bad run id {run_id!r}")
    f = state / run_id
    if op == "open":
        state.mkdir(parents=True, exist_ok=True)
        f.write_text(repr(time.time()))
        return {"env": {"WB_GATEWAY_KEY": caller_key(env["GATEWAY_KEY_SECRET"], JUDGE)}}
    if op != "close":
        raise SystemExit("judge-meter open|close RUN_ID")
    import psycopg
    import secrets as _secrets
    import urllib.request
    start = float(f.read_text())
    # the gateway writes its record a few seconds after each call: a marker call of the meter's own, made once the
    # run is over, under an id the run cannot know, closes the window once it is in the record
    marker = "judge-meter-" + _secrets.token_hex(12)
    key = caller_key(env["GATEWAY_KEY_SECRET"], JUDGE)
    req = urllib.request.Request(f"http://127.0.0.1:{env.get('GATEWAY_PORT') or 8090}/v1/embeddings",
                                 json.dumps({"model": env.get("WORKBENCH_EMBED_MODEL") or "ollama/qwen3-embedding:0.6b",
                                             "input": "x"}).encode(),
                                 {"Content-Type": "application/json", "x-bf-vk": key, "x-wb-call": marker})
    urllib.request.urlopen(req, timeout=60).read()
    url = f"postgresql://gateway_meter:{env['GATEWAY_METER_PASSWORD']}@127.0.0.1:{env.get('DB_PORT') or 5432}/gateway"
    q = """with w as (select timestamp as until from logs where metadata::jsonb->>'x-wb-call' = %s)
           select count(*), count(*) filter (where status = 'processing'), coalesce(sum(prompt_tokens), 0),
                  coalesce(sum(completion_tokens), 0), coalesce(sum(cost), 0), count(*) filter (where status = 'success'),
                  (select count(*) from w)
             from logs where virtual_key_name = %s and timestamp >= to_timestamp(%s)
              and timestamp <= coalesce((select until from w), 'infinity')
              and coalesce(metadata::jsonb->>'x-wb-call', '') <> %s"""
    with psycopg.connect(url, connect_timeout=5) as c:
        for _ in range(120):
            calls, busy, tin, tout, usd, ok, seen = c.execute(q, (marker, JUDGE, start, marker)).fetchone()
            if seen and not busy:
                break
            time.sleep(0.5)
        else:
            raise SystemExit("the gateway's record did not show the meter's marker call within a minute")
    f.unlink(missing_ok=True)
    return {"calls": calls, "answered": ok, "tokens": int(tin) + int(tout), "tokens_in": int(tin),
            "tokens_out": int(tout), "cost": float(usd)}


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "meter":
        print(json.dumps(meter(settings(), sys.argv[2:])))
    elif cmd == "judge-meter" and len(sys.argv) == 4:
        print(json.dumps(judge_meter(settings(), sys.argv[2], sys.argv[3])))
    elif cmd == "init":
        init(settings())
    elif cmd == "keys":
        print("\n".join(callers()))
    elif cmd == "render":
        env = settings()
        cfg = render(env)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(cfg, indent=2) + "\n")
        OUT.chmod(0o644)
        print(f"  wrote {OUT.relative_to(ROOT)}: providers {', '.join(cfg['providers']) or 'none'};"
              f" {len(cfg['governance']['virtual_keys'])} callers with keys")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
