"""The MCP router trial's cases for Substrate's own router (S-205: mcp-router/, Go), against the running stack: the
router at ROUTER_URL (its /mcp and /api), the kernel's connector from compose, and the trial's stdio tools server
connected as `tools` by run.sh. Tokens are the kernel's own (HS256, a `role` claim; KK_JWT_SECRET by name, never
printed). One line per case; results to .state/trials/mcp-router/ours.json. Standard library only.

The gate is the environment's: a read tool runs at once; a world-changing one waits as a proposal that a person other
than the caller decides (on the router's page, here through its API), and the call is recorded whatever happens.
"""
import json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as base  # noqa: E402  (its token minting and MCP session; ROUTER_URL, DECIDE_URL unused here)

URL = os.environ["ROUTER_URL"]
API = URL.rsplit("/mcp", 1)[0] + "/api"
OUT = Path(__file__).resolve().parents[3] / ".state/trials/mcp-router"
results = base.results
check = base.check


def api(path, tok, body=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None,
                                 {"content-type": "application/json", "authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def outcome(s, action):
    code, ok, text = s.call("router_outcome", {"action": action})
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text}


def action_of(text):
    import re
    m = re.search(r"action (\d+)", text)
    return int(m.group(1)) if m else None


STATE = OUT / "ours-phase.json"
owner, agent = base.token("person_owner"), base.token("agent_claude_code")


def phase1():
    owner, agent = base.token("person_owner"), base.token("agent_claude_code")
    code, _ = base.Session(None).start()
    check("refuses a call with no token", code in (401, 403), code)
    code, _ = base.Session(base.token("person_owner", "not-the-kernel-secret-but-32-chars-long")).start()
    check("refuses a token signed with another secret", code in (401, 403), code)
    me = base.Session(owner)
    code, r = me.start()
    check("takes the kernel's own token (HS256, role claim), as it is today", code == 200 and "result" in r, (code, r))
    check("answers initialize at 2025-11-25", (r.get("result") or {}).get("protocolVersion") == "2025-11-25", r.get("result"))
    code, r = me.rpc("tools/list")
    names = [t["name"] for t in (r.get("result") or {}).get("tools", [])]
    check("lists both servers' tools as one", "tools_echo" in names and "tools_write_note" in names
          and any(n.startswith("kernel_") for n in names) and "router_outcome" in names, names)
    code, ok, text = me.call("tools_echo", {"text": "hello"})
    check("a read tool runs at once", ok and "hello" in text, text)
    code, ok, text = me.call("kernel_recall", {"question": "what is substrate"}) if "kernel_recall" in names else (0, False, "no kernel_recall")
    check("the kernel answers as the caller (its token minted for the caller's role)", ok and "no bearer token" not in text
          and "invalid token" not in text, text[:200])

    ag = base.Session(agent)
    ag.start()
    code, ok, text = ag.call("tools_write_note", {"text": "from the agent"})
    held = action_of(text)
    check("a world-changing call is held as a proposal", not ok and held and "waits" in text, text)
    code, body = api("/decide", agent, {"action": held, "approve": True, "reason": "self"})
    check("an agent cannot decide (the page is a person's)", code in (401, 403), (code, body))
    code, ok, text = me.call("tools_write_note", {"text": "from the owner"})
    own = action_of(text)
    code, body = api("/decide", owner, {"action": own, "approve": True, "reason": "my own"})
    check("a person cannot approve their own call", code >= 400, (code, body))
    STATE.write_text(json.dumps({"held": held, "own": own, "results": results}))


def phase2():
    st = json.loads(STATE.read_text())
    held, own = st["held"], st["own"]
    results[:0] = st["results"]
    me2 = base.Session(owner)
    me2.start()
    code, body = api("/decide", owner, {"action": held, "approve": True, "reason": "fine"})
    check("after a router restart, a person approves the held call on the page's API", code == 200, (code, body))
    o = {}
    for _ in range(40):
        o = outcome(me2, held)
        if o.get("status") in ("applied", "failed"):
            break
        time.sleep(0.5)
    check("approved, it is applied by its server's connector, the result kept", o.get("status") == "applied"
          and "written" in json.dumps(o.get("result")), o)
    code, calls = api("/calls?limit=50", owner)
    mine = [c for c in calls if c.get("id") in (held, own)] if isinstance(calls, list) else []
    check("every call is in the record: tool, caller, gate, status, who decided", len(mine) == 2 and any(
          c["id"] == held and c["caller"] == "agent_claude_code" and c["gate"] == "propose" and c["decided_by"] == "person_owner"
          for c in mine), mine)
    check("the record also has the read calls, at their free gate", isinstance(calls, list) and any(
          c.get("tool") == "tools_echo" and c.get("gate") == "free" and c.get("status") == "applied" for c in calls), "")
    t0 = time.time()
    for i in range(20):
        me2.call("tools_echo", {"text": str(i)})
    check("a read call's round trip through the queue (mean of 20)", True, f"{(time.time() - t0) / 20 * 1000:.0f} ms each")
    results[-1]["detail"] = f"{(time.time() - t0) / 20 * 1000:.0f} ms each"
    print("  " + results[-1]["detail"])
    (OUT / "ours.json").write_text(json.dumps(results, indent=1))
    STATE.unlink()
    print(f"ours: {sum(r['ok'] for r in results)}/{len(results)} cases")


if __name__ == "__main__":
    phase1() if os.environ.get("PHASE", "1") == "1" else phase2()
