#!/usr/bin/env python3
"""Observe a system as it runs (OBSERVE.md): read the host, the container engine and what observe.yaml lists, and
write one snapshot per thing read to .state/observed/<host>/, for substrate:observed to turn into claims.

    python3 plugins/substrate/observe.py [ROOT]     # ROOT holds observe.yaml (default: the current directory)

It runs on the host, since reading a machine needs the machine. It knows no system by name: what to fetch and how
to read a kind of software come from observe.yaml. Values that may be secret are never written: environment and
.env values, headers, URL queries, and any key that names a password, secret, token or credential. Each snapshot
keeps only the fields it lists, so what the engine adds later is not written by default.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

SECRETISH = re.compile(r"(pass(word|wd)?|secret|token|credential|api[_-]?key|private[_-]?key|authorization|cookie)$", re.I)
REGISTRATION = re.compile(r"wb\.(view|menu|command|widget|app)\(\{\s*id:\s*'([^']+)'(?:[^\n]*?title:\s*(?:\(\)\s*=>\s*)?'([^']*)')?")


def scrub(v):
    """A copy with any value under a secret-sounding key dropped."""
    if isinstance(v, dict):
        return {k: ("[not kept]" if SECRETISH.search(str(k)) and not isinstance(x, (dict, list)) else scrub(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [scrub(x) for x in v]
    return v


def bare_url(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme, p.hostname + (f":{p.port}" if p.port else "") if p.hostname else p.netloc, p.path, "", ""))


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout if p.returncode == 0 else p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def engine_json(engine: str, *args: str):
    code, out = run([engine, *args])
    return json.loads(out) if code == 0 and out.strip() else None


def fetch(url: str, headers: dict | None = None, body: bytes | None = None) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "substrate-observe", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read(), r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("content-type", "")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(e).encode(), "text/plain"


# ------------------------------------------------------------------ the host
def read_host(engine: str) -> dict:
    osr = {}
    if Path("/etc/os-release").is_file():
        for line in Path("/etc/os-release").read_text().splitlines():
            k, _, v = line.partition("=")
            if k in ("NAME", "VERSION_ID", "PRETTY_NAME", "ID"):
                osr[k] = v.strip('"')
    mem = None
    if Path("/proc/meminfo").is_file():
        m = re.search(r"^MemTotal:\s+(\d+) kB", Path("/proc/meminfo").read_text(), re.M)
        mem = int(m.group(1)) * 1024 if m else None
    model = None
    if Path("/proc/cpuinfo").is_file():
        m = re.search(r"^model name\s*:\s*(.+)$", Path("/proc/cpuinfo").read_text(), re.M)
        model = m.group(1).strip() if m else None
    version = engine_json(engine, "version", "--format", "json") or {}
    client = version.get("Client") or {}
    server = version.get("Server") or {}
    return {"hostname": socket.gethostname(), "os": osr, "kernel": platform.release(), "arch": platform.machine(),
            "cpus": os.cpu_count(), "cpu_model": model, "memory_bytes": mem,
            "engine": {"name": engine, "version": client.get("Version") or server.get("Version"),
                       "api_version": client.get("APIVersion") or server.get("APIVersion")}}


# ------------------------------------------------------------------ the engine: containers, images, volumes
def read_containers(engine: str) -> list[dict]:
    listed = engine_json(engine, "ps", "-a", "--format", "json") or []
    ids = [c.get("Id") or c.get("ID") for c in listed]
    out = []
    for d in (engine_json(engine, "inspect", *ids) if ids else None) or []:
        cfg, hc, st = d.get("Config") or {}, d.get("HostConfig") or {}, d.get("State") or {}
        labels = cfg.get("Labels") or {}
        nets = (d.get("NetworkSettings") or {}).get("Networks") or {}
        ports = []
        for cport, binds in ((d.get("NetworkSettings") or {}).get("Ports") or {}).items():
            for b in binds or []:
                ports.append({"container": cport, "host_ip": b.get("HostIp"), "host_port": b.get("HostPort")})
        out.append({
            "id": d.get("Id"), "name": (d.get("Name") or "").lstrip("/"),
            "project": labels.get("com.docker.compose.project"), "service": labels.get("com.docker.compose.service"),
            "image": d.get("ImageName") or cfg.get("Image"), "image_id": d.get("Image"), "digest": d.get("ImageDigest"),
            "state": st.get("Status"), "health": (st.get("Health") or {}).get("Status") or None,
            "started_at": st.get("StartedAt"), "restart_policy": (hc.get("RestartPolicy") or {}).get("Name"),
            "user": cfg.get("User") or None, "read_only": hc.get("ReadonlyRootfs"),
            "cap_drop": hc.get("CapDrop"), "security_opt": hc.get("SecurityOpt"),
            "ports": ports,
            "mounts": [{"type": m.get("Type"), "name": m.get("Name"), "source": m.get("Source"),
                        "destination": m.get("Destination"), "rw": m.get("RW")} for m in d.get("Mounts") or []],
            "networks": {n: {"aliases": v.get("Aliases") or []} for n, v in nets.items()},
            "env_names": sorted({e.split("=", 1)[0] for e in cfg.get("Env") or []}),
            "labels": {k: v for k, v in labels.items() if not SECRETISH.search(k)},
            "compose_working_dir": labels.get("com.docker.compose.project.working_dir"),
            "compose_files": labels.get("com.docker.compose.project.config_files"),
        })
    return out


def read_images(engine: str, containers: list[dict]) -> list[dict]:
    ids = sorted({c["image_id"] for c in containers if c.get("image_id")})
    out = []
    for d in (engine_json(engine, "image", "inspect", *ids) if ids else None) or []:
        out.append({"id": d.get("Id"), "tags": d.get("RepoTags") or [], "digests": d.get("RepoDigests") or [],
                    "digest": d.get("Digest"), "created": d.get("Created"), "size": d.get("Size"),
                    "labels": {k: v for k, v in ((d.get("Config") or {}).get("Labels") or {}).items()
                               if k.startswith("org.opencontainers.image.")}})
    return out


def read_volumes(engine: str) -> list[dict]:
    names = [v.get("Name") for v in engine_json(engine, "volume", "ls", "--format", "json") or []]
    out = []
    for d in (engine_json(engine, "volume", "inspect", *names) if names else None) or []:
        out.append({"name": d.get("Name"), "driver": d.get("Driver"), "mountpoint": d.get("Mountpoint"),
                    "created": d.get("CreatedAt"), "labels": d.get("Labels") or {}})
    return out


# ------------------------------------------------------------------ files: setting names and Claude Code's wiring
def read_env_files(root: Path, files: list[str]) -> list[dict]:
    out = []
    for rel in files:
        f = root / rel
        if f.is_file():
            keys = [{"name": m.group(1), "line": n} for n, line in enumerate(f.read_text().splitlines(), 1)
                    if (m := re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line))]
            out.append({"file": rel, "keys": keys})
    return out


def read_claude_code(root: Path, files: list[str]) -> dict:
    out = {"settings": [], "mcp_servers": []}
    for rel in files:
        f = root / rel
        if not f.is_file():
            continue
        d = json.loads(f.read_text())
        if "mcpServers" in d:
            for name, s in (d.get("mcpServers") or {}).items():
                out["mcp_servers"].append({"file": rel, "name": name, "type": s.get("type") or ("stdio" if s.get("command") else None),
                                           "url": bare_url(s["url"]) if s.get("url") else None,
                                           "command": Path(s["command"]).name if s.get("command") else None,
                                           "auth": "headersHelper" if s.get("headersHelper") else "headers" if s.get("headers") else None,
                                           "env_names": sorted(s.get("env") or {})})
        else:
            perms = d.get("permissions") or {}
            out["settings"].append({
                "file": rel, "keys": sorted(d),
                "env_names": sorted(d.get("env") or {}),
                "hooks": {e: sum(len(g.get("hooks") or []) for g in gs or []) for e, gs in (d.get("hooks") or {}).items()},
                "permissions": {k: (len(v) if isinstance(v, list) else v) for k, v in perms.items()},
                "enabled_plugins": sorted(d.get("enabledPlugins") or {}),
                "enabled_mcp_servers": d.get("enabledMcpjsonServers") or []})
    return out


# ------------------------------------------------------------------ HTTP: what is served
def read_http(ep: dict, token: dict | None) -> dict:
    url, kind = ep["url"], ep.get("kind", "json")
    headers = dict(token or {}) if ep.get("auth") == "token" else {}
    snap = {"name": ep["name"], "url": bare_url(url), "kind": kind}
    if kind == "mcp":
        headers.update({"Content-Type": "application/json", "Accept": "application/json"})
        status, body, ctype = fetch(url, headers, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode())
        snap["status"] = status
        try:
            tools = json.loads(body)["result"]["tools"]
            snap["data"] = {"tools": [{"name": t["name"], "description": (t.get("description") or "")[:300]} for t in tools]}
        except (ValueError, KeyError, TypeError):
            snap["error"] = body[:300].decode(errors="replace")
        return snap
    status, body, ctype = fetch(url, headers)
    snap["status"] = status
    if status != 200:
        snap["error"] = body[:300].decode(errors="replace")
        return snap
    if kind == "shell":
        page = body.decode(errors="replace")
        modules = re.findall(r'<meta name="wb-plugin" content="([^"]+)">', page)
        found = []
        for m in modules:
            murl = urllib.parse.urljoin(url, m)
            s, src, _ = fetch(murl)
            regs = []
            if s == 200:
                for n, line in enumerate(src.decode(errors="replace").splitlines(), 1):
                    for r in REGISTRATION.finditer(line):
                        regs.append({"kind": r.group(1), "id": r.group(2), "title": r.group(3), "line": n,
                                     "quote": line.strip()[:200]})
            found.append({"module": m, "status": s, "sha256": hashlib.sha256(src).hexdigest() if s == 200 else None,
                          "registrations": regs})
        snap["data"] = {"modules": found, "page_sha256": hashlib.sha256(body).hexdigest()}
        return snap
    try:
        snap["data"] = scrub(json.loads(body))
    except ValueError:
        snap["error"] = "not JSON"
    if kind == "openapi" and isinstance(snap.get("data"), dict):
        d = snap["data"]                      # keep the paths and their operations, not every schema
        snap["data"] = {"openapi": d.get("openapi") or d.get("swagger"), "info": d.get("info"),
                        "paths": {p: {m: {"summary": (o or {}).get("summary") or ""} for m, o in ops.items()
                                      if m in ("get", "post", "put", "patch", "delete")}
                                  for p, ops in (d.get("paths") or {}).items()}}
    return snap


# ------------------------------------------------------------------ probes: a kind of software, inside its container
def read_probe(engine: str, probe: dict, container: dict) -> dict:
    code, out = run([engine, "exec", container["id"], *probe["exec"]], timeout=20)
    snap = {"container": container["name"], "kind": probe["kind"], "exec": probe["exec"], "status": code}
    try:
        data = json.loads(out) if code == 0 else None
    except ValueError:
        data = None
    if data is None:
        snap["error"] = out[:300]
    elif probe["kind"] == "caddy":
        servers = ((data.get("apps") or {}).get("http") or {}).get("servers") or {}
        snap["data"] = {"servers": scrub({n: {"listen": s.get("listen"), "routes": s.get("routes") or []} for n, s in servers.items()})}
    else:
        snap["data"] = scrub(data)
    return snap


def main(root: Path) -> int:
    cfg = yaml.safe_load((root / "observe.yaml").read_text()) if (root / "observe.yaml").is_file() else {}
    engine = os.environ.get("CONTAINER_ENGINE") or cfg.get("engine") or ("podman" if shutil.which("podman") else "docker")
    host = socket.gethostname()
    out = root / ".state" / "observed" / re.sub(r"[^A-Za-z0-9._-]", "-", host)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    when = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    written = []

    def write(name: str, read: str, data):
        doc = {"observed_at": when, "host": host, "read": read, "data": data}
        raw = json.dumps(doc, indent=1, sort_keys=True, default=str).encode()
        (out / f"{name}.json").write_bytes(raw)
        written.append({"name": name, "read": read, "sha256": hashlib.sha256(raw).hexdigest()})

    write("host", "the host: /etc/os-release, uname, /proc, the engine's version", read_host(engine))
    containers = read_containers(engine)
    write("containers", f"{engine} ps -a; {engine} inspect", containers)
    write("images", f"{engine} image inspect", read_images(engine, containers))
    write("volumes", f"{engine} volume ls; {engine} volume inspect", read_volumes(engine))
    write("env-files", "keys only: " + ", ".join(cfg.get("env_files") or []), read_env_files(root, cfg.get("env_files") or []))
    write("claude-code", "Claude Code's project wiring: " + ", ".join(cfg.get("claude_code") or []),
          read_claude_code(root, cfg.get("claude_code") or []))

    token = None
    if cfg.get("token"):
        code, got = run([str(root / cfg["token"])], cwd=root)
        token = json.loads(got) if code == 0 and got.strip().startswith("{") else None
    for ep in cfg.get("http") or []:
        write(f"http-{ep['name']}", f"GET {bare_url(ep['url'])}" if ep.get("kind") != "mcp" else f"MCP tools/list at {bare_url(ep['url'])}",
              read_http(ep, token))
    for probe in cfg.get("probes") or []:
        for c in containers:
            repo = (c.get("image") or "").rsplit("/", 1)[-1].split(":")[0]
            if repo == probe["image"] and c.get("state") == "running":
                write(f"probe-{c['name']}-{probe['kind']}", f"{engine} exec {c['name']} {' '.join(probe['exec'])}",
                      read_probe(engine, probe, c))
    for cmd in cfg.get("commands") or []:
        code, got = run(cmd["run"], cwd=root, timeout=120)
        try:
            data = scrub(json.loads(got)) if code == 0 else {"error": got[:300]}
        except ValueError:
            data = {"error": "not JSON"}
        write(f"command-{cmd['name']}", " ".join(cmd["run"]), {"kind": cmd.get("kind"), "status": code, "data": data})

    (out / "index.json").write_text(json.dumps({"observed_at": when, "host": host, "engine": engine,
                                                "snapshots": written}, indent=1))
    print(f"{len(written)} snapshots in {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()))
