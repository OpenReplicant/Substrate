"""OpenBao for substrate's scripts (S-31): log in as `substrate` (userpass, password in .state/openbao/keys/scripts.pw)
and read or write substrate/<NAME> (kv-v2, field "value"). Standard library only; never through a proxy.

    python3 scripts/secrets/bao.py get NAME        # the value on stdout ("" if unset)
    python3 scripts/secrets/bao.py put NAME        # the value on stdin
    python3 scripts/secrets/bao.py wait | status
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADDR = os.environ.get("BAO_ADDR", "http://127.0.0.1:8200")
OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(ADDR + "/v1/" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"X-Vault-Token": token} if token else {})})
    try:
        with OPEN.open(req, timeout=10) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except ValueError:
            return e.code, {}


def login() -> str:
    pw = (ROOT / ".state/openbao/keys/scripts.pw").read_text().strip()
    code, out = call("POST", "auth/userpass/login/substrate", {"password": pw})
    if code != 200:
        sys.exit(f"OpenBao refused the scripts' login ({code}); scripts/secrets.sh status")
    return out["auth"]["client_token"]


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "wait":
        for _ in range(60):
            try:
                code, h = call("GET", "sys/health")
                if h.get("initialized") and not h.get("sealed"):
                    return 0
            except OSError:
                pass
            time.sleep(1)
        return 1
    if cmd == "status":
        try:
            _, h = call("GET", "sys/health")
        except OSError:
            print("OpenBao is not answering (scripts/secrets.sh start)")
            return 1
        print(f"OpenBao {h.get('version')} at {ADDR}, " + ("unsealed" if not h.get("sealed") else "sealed"))
        return 0 if h.get("initialized") and not h.get("sealed") else 1
    if cmd in ("get", "put") and len(argv) == 2:
        token, name = login(), argv[1]
        if cmd == "get":
            code, out = call("GET", f"substrate/data/{name}", token=token)
            if code == 404:
                return 0
            if code != 200:
                sys.exit(f"OpenBao: reading {name} failed ({code})")
            sys.stdout.write(str(out["data"]["data"].get("value", "")))
            return 0
        value = sys.stdin.read().rstrip("\n")
        code, _ = call("POST", f"substrate/data/{name}", {"data": {"value": value}}, token=token)
        if code not in (200, 204):
            sys.exit(f"OpenBao: writing {name} failed ({code})")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
