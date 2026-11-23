"""The desktop spike (S-200), in a real browser against the running stack: the kernel's shell as a desktop at the front
door (127.0.0.1:8080), its windows, two framed apps on origins of their own, the bridge, and the headers. Results and
screenshots go to .state/trials/desktop/. Runs in the map-diagram trial's pinned Playwright image (run.sh).

Checks:
- sign in as a person (KK_PERSON, password in KK_PASSWORD); the token box is a plain text box with autofill off
- the launcher lists the kernel's tools, the view modules and the apps from /ui/apps.json
- windows open, come to the front when focused, minimise, close; the graph draws in its window
- each app loads in a sandboxed frame from its own origin, and the frame is not the shell's origin
- the bridge: a framed app's {kk: 'title'} message renames its window; the same message from anywhere else does not
- a page on an origin not in the shell's frame-src cannot be framed (the CSP refuses it)
- no page errors; no CSP violations but the one provoked
"""
import json, os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("DESKTOP_URL", "http://127.0.0.1:8080")
OUT = Path(__file__).resolve().parents[3] / ".state/trials/desktop"
OUT.mkdir(parents=True, exist_ok=True)
checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail, flush=True)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors, csp = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: csp.append(m.text) if "Content Security Policy" in m.text or "Refused to" in m.text else None)
    warned = []
    page.on("console", lambda m: warned.append(m.text) if "escape its sandboxing" in m.text else None)

    page.goto(BASE + "/")
    token_box = page.get_by_label("Token")
    check("the token box is plain text with autofill off",
          token_box.get_attribute("type") == "text" and token_box.get_attribute("autocomplete") == "off")
    page.get_by_label("Name").fill(os.environ["KK_PERSON"])
    page.get_by_label("Password").fill(os.environ["KK_PASSWORD"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_function("() => (document.querySelector('.who .muted')?.textContent || '').includes('person')", timeout=15000)
    check("a person signs in", True)

    nav = page.locator("nav")
    groups = nav.locator("h2").all_text_contents()
    entries = [b.locator("span").first.text_content() for b in nav.get_by_role("button").all()]
    check("the launcher has the kernel's tools, the views and the apps", groups == ["Kernel", "Views", "Apps"]
          and {"Search", "Review", "Graph", "Model gateway", "Substrate's maps"} <= set(entries), (groups, entries))

    nav.get_by_role("button", name="Graph").click()
    page.wait_for_function("() => +document.getElementById('cy').dataset.nodes > 0", timeout=30000)
    check("the graph draws in its window", int(page.get_attribute("#cy", "data-nodes")) > 0, page.get_attribute("#cy", "data-nodes"))
    nav.get_by_role("button", name="Search").click()
    z = lambda w: int(page.eval_on_selector(f'[data-window="{w}"]', "e => +getComputedStyle(e).zIndex"))
    check("a new window opens in front", z("search") > z("graph"), (z("search"), z("graph")))
    page.locator('[data-window="graph"] .bar').click(position={"x": 60, "y": 10})
    check("clicking a window brings it to the front", z("graph") > z("search"), (z("graph"), z("search")))
    before = page.eval_on_selector('[data-window="graph"]', "e => [e.offsetLeft, e.offsetTop]")
    bar = page.locator('[data-window="graph"] .bar').bounding_box()
    page.mouse.move(bar["x"] + 80, bar["y"] + 10); page.mouse.down(); page.mouse.move(bar["x"] + 280, bar["y"] + 110, steps=5); page.mouse.up()
    after = page.eval_on_selector('[data-window="graph"]', "e => [e.offsetLeft, e.offsetTop]")
    check("a window moves by its title bar", after[0] - before[0] == 200 and after[1] - before[1] == 100, (before, after))
    page.locator('[data-window="search"] [aria-label="Minimise"]').click()
    page.locator('[data-window="search"]').wait_for(state="hidden", timeout=5000)
    check("a window minimises, and the launcher shows it", not page.locator('[data-window="search"]').is_visible()
          and "min" in (nav.get_by_role("button", name="Search").get_attribute("class") or ""))
    nav.get_by_role("button", name="Search").click()
    page.locator('[data-window="search"]').wait_for(state="visible", timeout=5000)
    check("the launcher restores it", page.locator('[data-window="search"]').is_visible())
    page.locator('[data-window="search"] [aria-label="Close"]').click()
    page.locator('[data-window="search"]').wait_for(state="hidden", timeout=5000)
    check("a window closes", not nav.get_by_role("button", name="Search").get_attribute("class"))

    hidden = page.evaluate("""() => { const open = new Set(Alpine.$data(document.body).open.filter(w => !w.min).map(w => w.id));
        return [...document.querySelectorAll('.window')].filter(e => e.offsetParent !== null && !open.has(e.dataset.window))
                                                       .map(e => e.dataset.window); }""")
    check("no window shows that is not open", not hidden, hidden)
    nav.get_by_role("button", name="Modules").click()
    page.wait_for_selector('.view[data-view="view-modules"] table', timeout=15000)
    check("a view module renders in its own window", page.locator('[data-window="view:view-modules"] .view table').count() == 1)

    frames = {}
    for app, title in (("gateway", "Model gateway"), ("maps", "Substrate's maps")):
        nav.get_by_role("button", name=title).click()
        el = page.locator(f'iframe[data-app="{app}"]')
        el.wait_for(state="visible", timeout=15000)
        page.wait_for_timeout(2500)
        f = el.element_handle().content_frame()
        frames[app] = f
        origin = f.evaluate("() => location.origin") if f else None
        body = f.evaluate("() => document.body ? document.body.innerText.length : 0") if f else 0
        check(f"{app}: loads in a frame from its own origin", origin and origin != BASE and body > 0, (origin, body))
        check(f"{app}: the frame is sandboxed, with no referrer and no permissions",
              el.get_attribute("sandbox") == "allow-scripts allow-forms allow-same-origin allow-popups allow-downloads"
              and el.get_attribute("referrerpolicy") == "no-referrer" and el.get_attribute("allow") == "")
        page.screenshot(path=str(OUT / f"desktop-{app}.png"))

    # the bridge
    frames["maps"].evaluate("() => parent.postMessage({kk: 'title', text: 'Maps, renamed by the app'}, '*')")
    page.wait_for_timeout(300)
    title = page.locator('[data-window="app:maps"] .bar strong').text_content()
    check("bridge: an app renames its own window", title == "Maps, renamed by the app", title)
    page.evaluate("() => window.postMessage({kk: 'title', text: 'forged'}, '*')")
    frames["gateway"].evaluate("() => parent.postMessage({kk: 'token'}, '*')")
    page.wait_for_timeout(300)
    titles = page.locator(".window .bar strong").all_text_contents()
    check("bridge: the same message from the shell's own page or an unknown kind does nothing", "forged" not in titles, titles)
    check("bridge: the token is in no frame", all("kk_token" not in (f.evaluate("() => { try { return JSON.stringify(sessionStorage) } catch (e) { return '' } }") or "")
                                                for f in frames.values()))

    # a page on an origin the shell does not list cannot be framed
    n = len(csp)
    page.evaluate("""() => { const f = document.createElement('iframe'); f.src = 'http://127.0.0.1:8090/';
                             f.id = 'stranger'; document.body.appendChild(f); }""")
    page.wait_for_timeout(1500)
    refused = [m for m in csp[n:] if "frame-src" in m]
    check("the CSP refuses to frame an origin not in apps.json", refused, csp[n:])
    del csp[n:]
    page.screenshot(path=str(OUT / "desktop.png"))
    # Chromium warns on any frame allowed scripts and same-origin; it matters only on the shell's own origin
    check("the sandbox warning comes once per app frame, none for any other window", len(warned) == 2, len(warned))
    check("no page errors", not errors, errors)
    check("no CSP violations (but the one provoked)", not csp, csp)
    browser.close()

ok = all(c["ok"] for c in checks)
(OUT / "results.json").write_text(json.dumps(checks, indent=1))
print(f"{sum(c['ok'] for c in checks)}/{len(checks)} checks", "passed" if ok else "FAILED")
sys.exit(0 if ok else 1)
