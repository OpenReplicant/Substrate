"""The papers agent's model handler (agent.yaml, `main`): one call to the model, through the gateway, with the paper's
abstract as the observation and the environment's actions offered as tools. The tool it calls is the step's action; the
environment's gate (environment.py) decides what stays. How a paper is shown and a reply read is reading.py's, which the
record pass uses too.

    make(slug, cfg, gateway, package_dir) registers the handler `slug` with the runner (ladder.handler)

Nothing here imports the store; `gateway` is the handlers plugin's Gateway, built with the caller's key (live) or the
one key a judged run holds.
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

from ladder import Answer, Escalate, handler


def make(slug: str, cfg: dict, gateway, package_dir: Path):
    package_dir = Path(package_dir)
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))
    import reading
    fixed = reading.instructions(package_dir, cfg)

    @handler(slug)
    def main(item, ask):
        if not gateway.ready():
            return Escalate("no gateway configured (gateway_url, and a key or the secret that derives one)")
        call_id = secrets.token_hex(12)
        meta = {"gateway_call": call_id, "model": cfg["model"]}
        code, r = gateway.chat(f"handler:{slug}", cfg["model"], reading.messages(fixed, item["observation"]),
                               int(cfg.get("max_tokens", 700)), call_id, tools=reading.tools(item.get("actions") or []))
        meta["usage"] = r.get("usage")
        if code != 200:
            msg = ((r.get("error") or {}).get("message") if isinstance(r.get("error"), dict) else r.get("error")) or ""
            return Escalate(f"gateway {code}: {str(msg)[:160]}", meta=meta)
        action, why = reading.action_of(r)
        if action is None:
            return Escalate(why, meta=meta)
        return Answer(action, 1.0, note="a tool call carries no confidence", meta=meta)

    return main
