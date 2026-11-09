"""The collector (observe.py) and the observed extractor's helpers, without an engine or a network: settings are kept
by name and never by value, wherever the value hides (environment, create command, .env, Claude Code's settings,
URL queries, secret-sounding keys); Caddy routes are named by what they match; a URL path finds its route.

    python3 plugins/substrate/tests/test_observe.py      (needs PyYAML)
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import observe  # noqa: E402
import substrate_plugin as sp  # noqa: E402

SECRET = "hunter2-not-for-files"

INSPECT = [{
    "Id": "abc", "Name": "/shop-web-1", "Image": "sha256:img", "ImageName": "docker.io/library/nginx:1.27", "ImageDigest": "sha256:d",
    "State": {"Status": "running", "Health": {"Status": "healthy"}},
    "Config": {"User": "", "Env": [f"DB_PASSWORD={SECRET}", "PATH=/usr/bin"], "CreateCommand": ["run", "-e", f"DB_PASSWORD={SECRET}"],
               "Labels": {"com.docker.compose.project": "shop", "com.docker.compose.service": "web", "vendor.api_token": SECRET}},
    "HostConfig": {"ReadonlyRootfs": True, "RestartPolicy": {"Name": "always"}},
    "NetworkSettings": {"Ports": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8000"}]},
                        "Networks": {"shop_default": {"Aliases": ["web", "shop-web-1"]}}},
    "Mounts": [{"Type": "volume", "Name": "shop_data", "Destination": "/data", "RW": True}]}]

observe.engine_json = lambda engine, *args: [{"Id": "abc"}] if args[0] == "ps" else INSPECT if args[0] == "inspect" else None
containers = observe.read_containers("docker")
dumped = json.dumps(containers)
assert SECRET not in dumped, "no environment value, create command or secret-sounding label is kept"
c = containers[0]
assert c["env_names"] == ["DB_PASSWORD", "PATH"], c["env_names"]
assert (c["project"], c["service"], c["health"], c["read_only"]) == ("shop", "web", "healthy", True)
assert c["networks"] == {"shop_default": {"aliases": ["web", "shop-web-1"]}}
assert c["ports"] == [{"container": "80/tcp", "host_ip": "0.0.0.0", "host_port": "8000"}]

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    (root / ".env").write_text(f"# a comment\nDB_PASSWORD={SECRET}\nexport MODE=dev\n")
    (root / "settings.json").write_text(json.dumps({"env": {"API_KEY": SECRET}, "hooks": {"Stop": [{"hooks": [{"command": "x"}]}]},
                                                    "permissions": {"allow": ["Bash(ls)"]}}))
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"wb": {"type": "http", "url": f"http://h:1/mcp?token={SECRET}",
                                                                      "headers": {"Authorization": SECRET}}}}))
    envs = observe.read_env_files(root, [".env"])
    cc = observe.read_claude_code(root, ["settings.json", ".mcp.json"])
    assert SECRET not in json.dumps(envs) + json.dumps(cc), "files are read for names only"
    assert [k["name"] for k in envs[0]["keys"]] == ["DB_PASSWORD", "MODE"] and envs[0]["keys"][0]["line"] == 2
    assert cc["settings"][0]["env_names"] == ["API_KEY"] and cc["settings"][0]["hooks"] == {"Stop": 1}
    assert cc["mcp_servers"][0]["url"] == "http://h:1/mcp" and cc["mcp_servers"][0]["auth"] == "headers"

assert observe.scrub({"a": {"password": SECRET, "token": SECRET, "key": "fine"}}) == \
    {"a": {"password": "[not kept]", "token": "[not kept]", "key": "fine"}}

# routes: named by what they match, found by path
assert sp.route_slug([{"path": ["/api/*"]}]) == "api-any"
assert sp.route_slug([{"path": ["/api"]}]) == "api"
assert sp.route_slug([{"path_regexp": {"name": "pluginweb", "pattern": "^/p/"}}]) == "re-pluginweb"
assert sp.route_slug(None) == "all"
assert sp.matches([{"path": ["/wb/api/*"]}], "/wb/api/mcp") and not sp.matches([{"path": ["/api/*"]}], "/wb/api/mcp")
assert sp.walk_handlers([{"handler": "subroute", "routes": [{"handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "app:3000"}]}]}]}]) \
    == (["subroute", "reverse_proxy"], ["app:3000"])

# nothing self-only: the collector and the extractor name no part of any one system
for f in ("observe.py", "substrate_plugin.py"):
    text = (Path(__file__).resolve().parents[1] / f).read_text()
    for name in ("substrate-caddy", "substrate-db", "substrate-postgrest", "substrate-tools", "workbench-mcp-tools", "rig"):
        assert f'"{name}' not in text and f"'{name}" not in text, f"{f} names {name}"

print("ok: test_observe")
