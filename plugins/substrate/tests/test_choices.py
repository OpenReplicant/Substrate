"""substrate:choices' registry reading, without the network: each value quotes the key it was read from, pre-releases
are skipped, deps.dev's newest version wins, and a registry that does not answer leaves its facts out.

    python3 plugins/substrate/tests/test_choices.py      (needs PyYAML; the Workbench container has it)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import substrate_plugin as sp  # noqa: E402

ANSWERS = {
    "https://api.github.com/repos/o/x": {"license": {"spdx_id": "MIT"}, "pushed_at": "2026-10-01T00:00:00Z",
                                         "stargazers_count": 7, "archived": False},
    "https://api.github.com/repos/o/x/releases?per_page=20": [
        {"tag_name": "v2.0-rc1", "prerelease": True, "published_at": "2026-10-01T00:00:00Z"},
        {"tag_name": "v1.9", "prerelease": False, "published_at": "2026-09-01T00:00:00Z"}],
    "https://api.deps.dev/v3/systems/maven/packages/g%3Aa": {"versions": [
        {"versionKey": {"version": "2.0"}, "publishedAt": "2026-08-01T00:00:00Z"},
        {"versionKey": {"version": "1.0"}, "publishedAt": "2025-01-01T00:00:00Z"}]},
    "https://api.deps.dev/v3/systems/maven/packages/g%3Aa/versions/2.0": {"licenses": ["Apache-2.0"]},
}


def fake(url):
    return (json.dumps(ANSWERS[url]).encode(), ANSWERS[url]) if url in ANSWERS else None


sp.fetch_json = fake


def merged(facts):
    out = {}
    for _, _, values, quotes in facts:
        for k, v in values.items():
            out[k] = (v, quotes[k]["quote"])
    return out


gh = merged(sp.registry_facts({"repository": "o/x"}))
assert gh["licence"] == ("MIT", '"spdx_id": "MIT"'), gh["licence"]
assert gh["latest_release"] == ("v1.9", '"tag_name": "v1.9"'), "pre-releases are skipped"
assert gh["released_on"][0] == "2026-09-01" and gh["last_push"][0] == "2026-10-01"

dd = merged(sp.registry_facts({"repository": "o/x", "package": {"system": "maven", "name": "g:a"}}))
assert dd["latest_release"][0] == "2.0", "deps.dev's newest version wins, and GitHub releases are not read"
assert dd["licence"] == ("Apache-2.0", '"licenses": ["Apache-2.0"]'), "a package's licence comes from deps.dev"

assert sp.registry_facts({"repository": "gone/away"}) == [], "no answer, no facts"
print("ok")
