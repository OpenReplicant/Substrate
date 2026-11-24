"""The desktop as an environment (S-206), end to end in a real browser against the stack: the trial's own test person (`trial`, so a live assistant, which hears only its person, does not answer it) signs in, opens the
Assistant and says something; an agent (its own token, through the MCP router) reads it, says something back, shows the
person an app and asks a question; each appears in the chat; the person answers the question (the answer replies to
it) and opens what was shown, which comes up in its own window; every agent action is in the router's record. Runs in
the map-diagram trial's Playwright image (assistant.sh). Secrets by name only."""
import json, os, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp-router"))
os.environ.setdefault("ROUTER_URL", "http://127.0.0.1:8083/mcp")
import run as base  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / ".state/trials/desktop"
checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail, flush=True)


agent = base.Session(base.token("agent_claude_code"))
agent.start()
stamp = str(int(time.time()))
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if "Content Security Policy" in m.text or "Refused to" in m.text else None)
    page.goto("http://127.0.0.1:8080/")
    page.get_by_label("Name").fill(os.environ["KK_PERSON"])
    page.get_by_label("Password").fill(os.environ["KK_PASSWORD"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_function("() => (document.querySelector('.who .muted')?.textContent || '').includes('person')", timeout=15000)
    page.locator("nav").get_by_role("button", name="Assistant").click()
    chat = page.locator('.view[data-view="view-assistant"]')
    chat.locator("textarea").wait_for(timeout=15000)
    check("the Assistant opens in its own window", True)
    said = f"Hello assistant, show me the maps please ({stamp})"
    chat.locator("textarea").fill(said)
    chat.locator("textarea").press("Enter")
    chat.locator(".msg.mine", has_text=stamp).wait_for(timeout=15000)
    check("the person's message shows as theirs", True)

    code, ok, text = agent.call("desktop_feed", {"person": "person_trial", "after": 0})
    heard = ok and stamp in text
    check("an agent reads it through the router (desktop_feed)", heard, text[-200:])
    code, ok, text = agent.call("desktop_say", {"text": f"Here are the maps ({stamp}).", "to": "person_trial"})
    check("an agent says something (desktop_say, free by the desktop's policy)", ok, text)
    code, ok, text = agent.call("desktop_show", {"kind": "app", "id": "app:maps", "title": "Substrate's maps", "to": "person_trial"})
    check("an agent shows the person an app (desktop_show)", ok, text)
    code, ok, text = agent.call("desktop_ask", {"question": f"Which map first? ({stamp})", "to": "person_trial"})
    asked = int(re.search(r"signal (\d+)", text).group(1)) if ok and re.search(r"signal (\d+)", text) else None
    check("an agent asks the person a question (desktop_ask)", ok and asked, text)

    chat.locator(".msg", has_text=f"Here are the maps ({stamp})").wait_for(timeout=30000)
    chat.locator('.msg[data-kind="show"]', has_text="Substrate's maps").last.wait_for(timeout=30000)
    ask = chat.locator('.msg[data-kind="ask"]', has_text=stamp).last
    ask.wait_for(timeout=30000)
    check("what the agent said, showed and asked appears in the chat", True)
    page.screenshot(path=str(OUT / "assistant.png"))
    ask.get_by_role("button", name="Answer").click()
    chat.locator("textarea").fill(f"The substrate map ({stamp})")
    chat.locator("textarea").press("Enter")
    chat.locator(".msg.mine", has_text=f"The substrate map ({stamp})").wait_for(timeout=15000)
    code, ok, text = agent.call("desktop_feed", {"person": "person_trial", "after": 0})
    rows = json.loads(text) if ok else []
    answer = next((r for r in rows if r["kind"] == "message" and f"The substrate map ({stamp})" in r["body"].get("text", "")), {})
    check("the person's answer replies to the question", answer.get("body", {}).get("reply_to") == asked, answer)
    chat.locator('.msg[data-kind="show"]', has_text="Substrate's maps").last.get_by_role("button").click()
    page.locator('iframe[data-app="maps"]').wait_for(state="visible", timeout=15000)
    check("the person opens what was shown: the app comes up in its own window", True)
    page.screenshot(path=str(OUT / "assistant-open.png"))
    code, calls = 0, []
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8083/api/calls?limit=50",
                                 headers={"authorization": "Bearer " + base.token("person_trial")})
    calls = json.loads(urllib.request.urlopen(req, timeout=10).read())
    done = {c["tool"] for c in calls if c["caller"] == "agent_claude_code" and c["status"] == "applied"
            and c["tool"].startswith("desktop_")}
    check("every agent action is in the router's record", {"desktop_say", "desktop_show", "desktop_ask", "desktop_feed"} <= done, done)
    check("no page errors or CSP violations", not errors, errors)
    b.close()
(OUT / "assistant.json").write_text(json.dumps(checks, indent=1))
print(f"{sum(c['ok'] for c in checks)}/{len(checks)} checks", "passed" if all(c["ok"] for c in checks) else "FAILED")
