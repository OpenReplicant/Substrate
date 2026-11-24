"""The MCP router's page (S-205) in a real browser, as a person uses it from the desktop: an agent's world-changing call
waits; the person signs in on the page (127.0.0.1:8083), sees it under Waiting with its tool and caller, approves it,
and the call is applied; the record and the tools show; no page errors or CSP violations. Runs in the map-diagram
trial's Playwright image (page.sh); KK_JWT_SECRET (to mint the agent's token) and the person's password by name."""
import json, os, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("ROUTER_URL", "http://127.0.0.1:8083/mcp")
import run as base  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / ".state/trials/mcp-router"
checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail, flush=True)


ag = base.Session(base.token("agent_claude_code"))
ag.start()
code, ok, text = ag.call("tools_write_note", {"text": "a note an agent wants to write"})
m = re.search(r"action (\d+)", text)
held = int(m.group(1)) if m else None
check("an agent's world-changing call waits", not ok and held, text)

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1200, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if "Content Security Policy" in m.text or "Refused to" in m.text else None)
    resp = page.goto("http://127.0.0.1:8083/")
    csp = resp.headers.get("content-security-policy", "")
    check("the page sends its CSP, framable by the desktop only", "frame-ancestors http://127.0.0.1:8080" in csp
          and "script-src 'self'" in csp, csp)
    page.fill("#signin input[name=name]", os.environ["KK_PERSON"])
    page.fill("#signin input[name=password]", os.environ["KK_PASSWORD"])
    page.click("#signin button[type=submit]")
    page.wait_for_selector("#app:not([hidden])", timeout=15000)
    check("a person signs in on the page with their kernel login", True)
    card = page.locator("#waiting > *", has_text="tools_write_note").first
    card.wait_for(timeout=15000)
    text = card.inner_text()
    check("the waiting call shows its tool and its caller", "tools_write_note" in text and "agent_claude_code" in text, text)
    page.screenshot(path=str(OUT / "page-waiting.png"))
    card.get_by_role("button", name="Approve").click()
    status = None
    for _ in range(30):
        status = json.loads(ag.call("router_outcome", {"action": held})[2]).get("status")
        if status in ("applied", "failed"):
            break
        time.sleep(0.5)
    check("approved on the page, the call is applied", status == "applied", status)
    page.wait_for_timeout(3500)
    rows = page.locator("#calls tr").count()
    tools = page.locator("#tools tr").count()
    check("the record and the tools show", rows > 3 and tools > 3, (rows, tools))
    page.screenshot(path=str(OUT / "page.png"), full_page=True)
    check("no page errors or CSP violations", not errors, errors)
    b.close()
(OUT / "page.json").write_text(json.dumps(checks, indent=1))
print(f"{sum(c['ok'] for c in checks)}/{len(checks)} checks", "passed" if all(c["ok"] for c in checks) else "FAILED")
