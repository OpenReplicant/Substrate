"""The MCP router trial's cases (S-204), run against one router at ROUTER_URL (streamable HTTP), with tokens minted the
kernel's way (HS256, a `role` claim; KK_JWT_SECRET, passed by name and never printed) and the decision service at
DECIDE_URL. One result line per case; results to .state/trials/mcp-router/<ROUTER>.json. Standard library only.

Cases: refuses no token and a token signed with another secret; takes the kernel's token; answers initialize at
2025-11-25; lists both backends' tools as one; a read tool passes; the kernel sees the caller (whoami through the
router); a world-changing tool is held until a person approves it, then goes; the decision service was asked with the
caller's role; an agent's token is limited to the read tool by a rule.
"""
import base64, hashlib, hmac, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

URL, DECIDE, NAME = os.environ["ROUTER_URL"], os.environ["DECIDE_URL"], os.environ.get("ROUTER", "router")
SECRET = os.environ.get("KK_JWT_SECRET", "")     # HS256 routers: the kernel's own secret, by name, never printed
EDKEY = os.environ.get("ED25519_KEY")              # routers that need an asymmetric key: a key made for the trial
OUT = Path(__file__).resolve().parents[3] / ".state/trials/mcp-router"
OUT.mkdir(parents=True, exist_ok=True)
results = []


def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


ISS = {"iss": "urn:kk:kernel", "aud": "urn:kk:mcp"} if os.environ.get("TOKEN_ISS") == "1" else {}


def token(role, secret=SECRET, claims=None):
    """The kernel's token (kk/cli.py mint: HS256, role, iat, exp); with TOKEN_ISS=1 also iss, aud and a kid in the
    header, as a router that requires them needs (a small change to the kernel's mint)."""
    now = int(time.time())
    body = {"role": role, "iat": now, "exp": now + 600, **(ISS if claims is None else claims)}
    if EDKEY:       # EdDSA (Ed25519), as the kernel would sign if a router takes only asymmetric keys (PyJWT in the kernel image)
        import jwt
        key = open(EDKEY).read() if secret is SECRET else __import__("cryptography.hazmat.primitives.asymmetric.ed25519",
              fromlist=["x"]).Ed25519PrivateKey.generate()     # "another secret": a key the router does not know
        return jwt.encode(body, key, algorithm="EdDSA", headers={"kid": "kernel"})
    head = {"alg": "HS256", "typ": "JWT", **({"kid": "kernel"} if ISS else {})}
    h, p = b64(json.dumps(head, separators=(",", ":")).encode()), b64(json.dumps(body).encode())
    return f"{h}.{p}.{b64(hmac.new(secret.encode(), f'{h}.{p}'.encode(), hashlib.sha256).digest())}"


def check(case, ok, detail=""):
    results.append({"router": NAME, "case": case, "ok": bool(ok), "detail": str(detail)[:400]})
    print(f"{NAME:14} {'ok  ' if ok else 'FAIL'} {case}" + ("" if ok else f"  {str(detail)[:200]}"), flush=True)


def post(url, body, headers=None):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json",
                                 "accept": "application/json, text/event-stream", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw, hdrs, code = r.read().decode(), dict(r.headers), r.status
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()
    if raw.lstrip().startswith(("event:", "data:")):           # an SSE answer: the last data line holding a response
        datas = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
        raw = next((d for d in reversed(datas) if '"id"' in d), datas[-1] if datas else "")
    return code, hdrs, raw


class Session:
    def __init__(self, tok):
        self.h = {"authorization": f"Bearer {tok}"} if tok else {}
        self.n = 0

    def rpc(self, method, params=None):
        self.n += 1
        code, hdrs, raw = post(URL, {"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}, self.h)
        sid = {k.lower(): v for k, v in hdrs.items()}.get("mcp-session-id")
        if sid:
            self.h["mcp-session-id"] = sid
        try:
            return code, json.loads(raw) if raw else {}
        except ValueError:
            return code, {"raw": raw[:300]}

    def start(self):
        code, r = self.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                          "clientInfo": {"name": "router-trial", "version": "0"}})
        if code == 200:
            post(URL, {"jsonrpc": "2.0", "method": "notifications/initialized"}, self.h)
            self.h["mcp-protocol-version"] = (r.get("result") or {}).get("protocolVersion", "2025-11-25")
        return code, r

    def call(self, name, args):
        code, r = self.rpc("tools/call", {"name": name, "arguments": args})
        res = r.get("result") or {}
        text = " ".join(c.get("text", "") for c in res.get("content", []))
        return code, (not res.get("isError") and "error" not in r and code == 200), text or json.dumps(r)[:300]


code, _ = Session(None).start()
check("refuses a call with no token", code in (401, 403), code)
code, _ = Session(token("person_owner", "not-the-kernel-secret-but-32-chars-long")).start()
check("refuses a token signed with another secret", code in (401, 403), code)
if ISS:
    code, _ = Session(token("person_owner", claims={})).start()
    check("(today's kernel token, without iss and aud)", True, f"answered {code}")
    results[-1]["detail"] = f"answered {code}"
me = Session(token("person_owner"))
code, r = me.start()
check(f"takes the kernel's token ({'EdDSA' if EDKEY else 'HS256'}, role claim)", code == 200 and "result" in r, (code, r))
check("answers initialize at 2025-11-25", (r.get("result") or {}).get("protocolVersion") == "2025-11-25", r.get("result"))
code, r = me.rpc("tools/list")
names = [t["name"] for t in (r.get("result") or {}).get("tools", [])]
find = lambda base: next((n for n in names if n == base or n.endswith("_" + base)), None)
check("lists both backends' tools as one", find("echo") and find("write_note") and find("whoami"), names[:40])
code, ok, text = me.call(find("echo") or "echo", {"text": "hello"})
check("a read tool passes", ok and "hello" in text, text)
code, ok, text = me.call(find("whoami") or "whoami", {})
check("the kernel sees the caller (whoami through the router)", ok and "person_owner" in text, text)
code, ok, text = me.call(find("write_note") or "write_note", {"text": "held?"})
check("a world-changing tool is held for a person", not ok, text)
urllib.request.urlopen(urllib.request.Request(DECIDE + "/approve", json.dumps({"tool": "write_note"}).encode(),
                                              {"content-type": "application/json"}), timeout=10).read()
code, ok, text = me.call(find("write_note") or "write_note", {"text": "approved"})
check("once a person approves it, it goes", ok and "written" in text, text)
log = json.loads(urllib.request.urlopen(DECIDE + "/log", timeout=10).read())
check("the decision service was asked, with the caller's role and the tool",
      any(e.get("tool") == "write_note" and "person_owner" in json.dumps(e) for e in log), log[-3:])
ag = Session(token("agent_claude_code"))
ag.start()
code, ok, text = ag.call(find("echo") or "echo", {"text": "agent"})
check("an agent's token may call the read tool", ok and "agent" in text, text)
code, ok, text = ag.call(find("write_note") or "write_note", {"text": "agent write"})
check("a rule limits an agent's token: no world-changing tool", not ok, text)
(OUT / f"{NAME}.json").write_text(json.dumps(results, indent=1))
print(f"{NAME}: {sum(r['ok'] for r in results)}/{len(results)} cases")
