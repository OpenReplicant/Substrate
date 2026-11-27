#!/usr/bin/env python3
"""The model gateway (S-77): Bifrost's config.json rendered from .env and the callers below.

    python3 scripts/gateway.py render     # writes .state/gateway/config.json (no secret in it: Bifrost reads env.NAME)
    python3 scripts/gateway.py keys       # the callers that get a key
    bin/in-tools python3 scripts/gateway.py init   # its database and logins, in the tools container (up.sh runs it)
    bin/in-tools python3 scripts/gateway.py prune  # drop limits from its store that config.json no longer has (up.sh)
    bin/in-tools python3 scripts/gateway.py meter CALL_ID...   # what the meter's login sees of these calls
    bin/in-tools python3 scripts/gateway.py meter-open|meter-close RUN_ID   # Morphogen's meter: a judged run's key and tag, then its counts (S-193)

Providers are the ones this machine has: OpenRouter when OPENROUTER_API_KEY is set (free models only, unless
GATEWAY_OPENROUTER_MODELS says otherwise), Ollama when OLLAMA_URL is set. Every call is logged by the gateway in its
own database (`gateway` on the stack's Postgres) without message content; a call with no key is refused; each
caller has its own virtual key (an hourly cap when GATEWAY_REQUESTS_PER_HOUR is set), named in .env or derived from
GATEWAY_KEY_SECRET (caller_key), so a caller's process can reach its key without it being stored. Keys and fields
from Bifrost v2.3.2's transports/config.schema.json (read 2026-11-11).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".state/gateway/config.json"


NAMES = ("POSTGRES_PASSWORD", "DB_PORT", "OPENROUTER_API_KEY", "OLLAMA_URL", "GATEWAY_OPENROUTER_MODELS",
         "GATEWAY_REQUESTS_PER_HOUR", "GATEWAY_DB_PASSWORD", "GATEWAY_METER_PASSWORD", "GATEWAY_KEY_SECRET",
         "GATEWAY_PORT", "ANTHROPIC_MODELS", "COMPANION_MODELS",
         "LLM_MODEL", "LLM_FAST_MODEL", "KERNEL_URL", "KK_AUTHENTICATOR_PASSWORD", "MCP_ROUTER_DB_PASSWORD",
         "MCP_CONNECTOR_DB_PASSWORD", "MCP_DESKTOP_DB_PASSWORD", "MCP_CHANNEL_DB_PASSWORD")


def settings() -> dict[str, str]:
    """The settings this needs, each through scripts/lib.sh's env_value (the secrets slot, S-31); kept in memory."""
    out = subprocess.run(["sh", "-c", '. "$(dirname "$0")/lib.sh"; for n in "$@"; do printf "%s=" "$n"; env_value "$n" | base64 -w0; echo; done',
                          str(ROOT / "scripts/gateway.sh"), *NAMES], capture_output=True, text=True, check=True).stdout
    return {k: base64.b64decode(v).decode().strip() for k, _, v in (l.partition("=") for l in out.splitlines()) if k}


def caller_key(secret: str, caller: str) -> str:
    """The virtual key a caller gets when .env names none: derived, so its process can compute it from the secret."""
    return "sk-bf-" + hmac.new(secret.encode(), caller.encode(), hashlib.sha256).hexdigest()[:40]


# Every caller, and the only providers each may use (S-83): the store's embeddings stay local. A caller is added
# here when a step needs one. Two local models (S-169): `local`, the slow one on the CPU, and `fast`, the small one on
# the GPU; both stay here. Morphogen's judged runs (S-193) reach the local models only, counted by its meter. The old
# assistant's callers (the companion, the voice head, the worker, the components judge) were retired in S-194; the
# Anthropic provider stays for a caller on a Claude login, held to ANTHROPIC_MODELS, though none has one now.
CALLERS = {"store:embed": ("ollama",), "morphogen:judge": ("local", "fast")}
LOCAL = ("ollama", "local", "fast")
FIXED_KEYS = {"store:embed": "STORE_EMBED_KEY"}   # keys read from .env by the gateway and the caller


def callers() -> list[str]:
    return sorted(CALLERS)


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
    # the local model on llama.cpp's server (compose service llm), OpenAI-compatible, no key
    if env.get("LLM_MODEL"):
        providers["local"] = {
            "keys": [{"name": "llm", "value": "no-key", "models": ["*"], "weight": 1.0}],   # llama-server has no --api-key: any value; an empty one counts as none
            "network_config": {"base_url": "http://llm:8080", "default_request_timeout_in_seconds": 300,
                               "allow_private_network": True},
            "custom_provider_config": {"base_provider_type": "openai",
                                       "allowed_requests": {"chat_completion": True, "chat_completion_stream": True}}}
    # the fast local model (compose service llm-fast, S-169), the same way
    if env.get("LLM_FAST_MODEL"):
        providers["fast"] = {
            "keys": [{"name": "llm-fast", "value": "no-key", "models": ["*"], "weight": 1.0}],
            "network_config": {"base_url": "http://llm-fast:8080", "default_request_timeout_in_seconds": 120,
                               "allow_private_network": True},
            "custom_provider_config": {"base_provider_type": "openai",
                                       "allowed_requests": {"chat_completion": True, "chat_completion_stream": True}}}
    # Anthropic with no key of its own: only calls carrying a Claude login can use it
    providers["anthropic"] = {"keys": []}
    allowed = {"local": ["*"], "fast": ["*"], "anthropic": [m.strip() for m in (env.get("ANTHROPIC_MODELS") or env.get("COMPANION_MODELS") or "regex:claude-haiku.*").split(",") if m.strip()],
               "openrouter": [m.strip() for m in (env.get("GATEWAY_OPENROUTER_MODELS") or "regex:.*:free").split(",") if m.strip()],
               "ollama": ["regex:.*"]}
    secret = env.get("GATEWAY_KEY_SECRET") or ""
    # OpenRouter's free tier limits the account (20 calls a minute, 1000 a day: the owner, 2026-11-11, S-87) and
    # answers 429 past it, which handlers take as the gateway's refusal and retry; a cap per caller is optional
    per_hour = int(env.get("GATEWAY_REQUESTS_PER_HOUR") or 0)
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
                            for c in callers() if not set(CALLERS.get(c, providers)) <= set(LOCAL)] if secret and per_hour else [],
            "virtual_keys": [{
                "id": "vk-" + c.replace(":", "-"), "name": c, "is_active": True,
                "value": f"env.{FIXED_KEYS[c]}" if c in FIXED_KEYS else caller_key(secret, c),
                "description": f"{c}'s calls, counted by the gateway",
                # the hourly cap guards a provider's quota; a caller held to local models has none to guard
                **({} if set(CALLERS.get(c, providers)) <= set(LOCAL) or not per_hour else {"rate_limit_id": "rl-" + c.replace(":", "-")}),
                "provider_configs": [{"provider": p, "allowed_models": allowed[p], "key_ids": ["*"]} for p in providers
                                     if p in CALLERS.get(c, providers)],
            } for c in callers()] if secret else [],
        },
    }


def init(env: dict[str, str]) -> None:
    """The gateway's database and its two logins, made once and kept: `gateway` owns the database (Bifrost makes
    its tables there), `gateway_meter` may only read them (the meter)."""
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


def prune(env: dict[str, str]) -> None:
    """Bifrost keeps each key's limit as a model rule in its store, and a later config.json without the limit does not
    remove it (seen 2026-11-11, S-87): drop the rules and limits the rendered config no longer has, so config.json
    stays the source. Run before the gateway (re)starts; in the tools container (psycopg)."""
    import psycopg
    cfg = json.loads(OUT.read_text())
    keep = [r["id"] for r in cfg["governance"]["rate_limits"]]
    url = f"postgresql://postgres:{env['POSTGRES_PASSWORD']}@127.0.0.1:{env.get('DB_PORT') or 5432}/gateway"
    with psycopg.connect(url, connect_timeout=5, autocommit=True) as c:
        # a fresh store: Bifrost makes its tables as it first starts, which may still be under way (first install,
        # 2026-11-27): with any of them missing there is nothing stale to drop
        tables = ("governance_rate_limits", "governance_model_configs", "governance_virtual_keys",
                  "governance_virtual_key_provider_configs", "config_providers")
        if not all(c.execute("select to_regclass(%s)", (t,)).fetchone()[0] for t in tables):
            print("  gateway store: new (its tables are not all made yet), nothing to prune")
            return
        n = c.execute("delete from governance_model_configs where rate_limit_id is not null and not rate_limit_id = any(%s)", (keep,)).rowcount
        for t in ("governance_virtual_keys", "governance_virtual_key_provider_configs", "config_providers"):
            c.execute(f"update {t} set rate_limit_id = null where rate_limit_id is not null and not rate_limit_id = any(%s)", (keep,))
        m = c.execute("delete from governance_rate_limits where not id = any(%s)", (keep,)).rowcount
    print(f"  gateway store: {n} stale model rules and {m} stale limits dropped")


def meter(env: dict[str, str], ids: list[str]) -> dict:
    """What the meter's login sees of these call ids (each row's caller, status, latency, and whether any content
    was kept), and whether that login can change the record. In the tools container: it needs psycopg."""
    import psycopg
    url = f"postgresql://gateway_meter:{env['GATEWAY_METER_PASSWORD']}@127.0.0.1:{env.get('DB_PORT') or 5432}/gateway"
    with psycopg.connect(url, connect_timeout=5) as c:
        rows = c.execute("""select metadata::jsonb->>'x-wb-call', virtual_key_name, status, latency,
                                   concat_ws(' ', input_history, output_message, content_summary, raw_request, raw_response),
                                   prompt_tokens, cached_read_tokens, upstream_latency
                              from logs where metadata::jsonb->>'x-wb-call' = any(%s)""", (ids,)).fetchall()
    with psycopg.connect(url, connect_timeout=5) as c:
        try:
            c.execute("delete from logs where false")
            writable = True
        except psycopg.Error:
            writable = False
    # prompt and cached tokens, and the provider's own latency: whether a log that only grows kept its cache (S-104)
    return {"rows": {r[0]: {"caller": r[1], "status": r[2], "latency": float(r[3]) if r[3] is not None else None, "content": r[4] or "",
                            "prompt_tokens": r[5], "cached_read_tokens": r[6], "upstream_latency": float(r[7]) if r[7] is not None else None}
                     for r in rows}, "writable": writable}


JUDGE_CALLER = "morphogen:judge"


def meter_open(env: dict[str, str], run_id: str) -> dict:
    """Morphogen's meter contract (plan step 2, S-193): what one judged run calls the gateway with: the judge's key
    (derived, local models only) and a tag it sends as x-wb-call, '<tag>-<n>', so its calls can be told apart."""
    return {"env": {"GATEWAY_KEY": caller_key(env["GATEWAY_KEY_SECRET"], JUDGE_CALLER), "GATEWAY_CALL_TAG": run_id}}


def meter_close(env: dict[str, str], run_id: str, settle: float = 1.0, quiet: int = 3) -> dict:
    """That run's counts from the gateway's own record, read by the meter's login once the count stops moving: the
    gateway writes its log in batches after the replies (a run's last calls arrived up to seconds late, seen
    2026-11-23), so it waits two seconds, then until `quiet` reads in a row agree. In the tools container (psycopg)."""
    import time
    import psycopg
    url = f"postgresql://gateway_meter:{env['GATEWAY_METER_PASSWORD']}@127.0.0.1:{env.get('DB_PORT') or 5432}/gateway"
    q = """select count(*), count(*) filter (where status <> 'success'), coalesce(sum(prompt_tokens), 0),
                  coalesce(sum(completion_tokens), 0), coalesce(sum(latency), 0)
             from logs where virtual_key_name = %s and metadata::jsonb->>'x-wb-call' like %s"""
    time.sleep(2)
    last, same, deadline = None, 0, time.monotonic() + 30
    with psycopg.connect(url, connect_timeout=5, autocommit=True) as c:
        while time.monotonic() < deadline:
            row = c.execute(q, (JUDGE_CALLER, run_id.replace("%", "") + "-%")).fetchone()
            same = same + 1 if row == last else 1
            last = row
            if same >= quiet:
                break
            time.sleep(settle)
    calls, errors, prompt, completion, latency = last
    return {"calls": calls, "errors": errors, "prompt_tokens": int(prompt), "completion_tokens": int(completion),
            "tokens": int(prompt) + int(completion), "latency_ms": float(latency)}


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "meter-open":
        print(json.dumps(meter_open(settings(), sys.argv[2])))
    elif cmd == "meter-close":
        print(json.dumps(meter_close(settings(), sys.argv[2])))
    elif cmd == "meter":
        print(json.dumps(meter(settings(), sys.argv[2:])))
    elif cmd == "init":
        init(settings())
    elif cmd == "prune":
        prune(settings())
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
