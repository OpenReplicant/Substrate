# Observing a system as it runs (spec step 5)

The observed half of a model, read from the machine itself, the way it would be read on any machine. Two
parts, because reading a machine needs the machine and Workbench's server is locked in its own container:

| Part | Runs | Reads | Writes |
| --- | --- | --- | --- |
| `observe.py` (collector) | on the host, `scripts/observe.sh` | the host, the container engine, HTTP endpoints, files, commands, as `observe.yaml` lists | snapshots, one JSON file per thing read, in `.state/observed/<host>/` |
| `substrate:observed` (extractor) | in Workbench's server | those snapshots, read-only | items and relations, each value a claim quoting its snapshot by JSON pointer |

**Self is not a special case.** `observe.yaml` says where to look (which endpoints, files and commands) and how to
read a kind of software (probes keyed on an image's name, e.g. Caddy's admin API); nothing in the collector or
the extractor names substrate. Another system is another `observe.yaml`, or another host's snapshot folder.

**Secrets.** Settings are observed by name, never value: the collector drops every environment value, every
`.env` value and every header before a snapshot is written, and `scripts/observe.sh` runs gitleaks over the
snapshot folder before the extractor may read it. A token needed to read an endpoint is held in memory only.

## What is observed

| Type | From | Fields | Relations |
| --- | --- | --- | --- |
| `host` | `/etc/os-release`, `uname`, `/proc/cpuinfo`, `/proc/meminfo`, the engine's version | os, kernel, arch, cpus, cpu_model, memory_bytes, engine, engine_version | runs container |
| `container` | the engine's `ps` and `inspect` | name, project, service, image, digest, state, health, started_at, ports, mounts, networks (with aliases), read_only, user, restart_policy, env_names | the host runs it; runsImage, mounts volume |
| `image` | the engine's `image inspect` | tags, digest, repo_digests, created, size, labels | |
| `volume` | the engine's `volume inspect` | driver, mountpoint, labels, used_by | |
| `setting` | container environment (names), `.env` keys, Claude Code's settings keys and env names | name, where, of, line | configures container |
| `route` | Caddy's admin API (`/config/`), as it runs, not as written | server, listen, match, handlers, upstreams, order | the web server's container serves it; it proxiesTo the container an upstream's host is an alias of |
| `api` | an OpenAPI document or an MCP `tools/list`, fetched | url, kind, api_title, version, operations | servedBy the route its URL reaches (the container publishing the port, its first matching route) |
| `plugin` | Workbench's `/wb/api/health`, `/wb/api/extractors`, `/api/content_types` | version, server, content_types, extractors, error | |
| `ui` | the shell's page as served (`/`), and each module it loads | module, plugin, views, menus, commands, widgets, sha256 | servedBy route |
| `connection` | Claude Code's `.mcp.json` (project wiring) | client, file, url, transport, command, auth | connectsTo the api at its URL |
| `cell` | `morphogen status` | ref, role, owner, ready, cell_source | cellOf the map's component |

Each item cites the snapshot it came from (`file:.state/observed/<host>/<name>.json`, its sha256 in Workbench)
and quotes the value at its JSON pointer.

## Drift for every kind

The map says how a declared part is recognised when it runs: `substrate.dev/observed-as` on a catalog entry, a
list of `<type>:<slug>` (e.g. `container:substrate-caddy`, `route:srv0-api`). `substrate:drift` then raises:

- **undeclared**: an observed container, volume, route, api, plugin, ui or connection no declared part names;
- **unobserved**: an `observed-as` ref with nothing observed by that name;

beside step 2's skills and hooks. Each gap goes to the review lane and is withdrawn once it closes either way.
Settings and images are not gaps on their own: they belong to the container that has them.

## Check

The step 5 check in `docs/build.yaml`. In short: every row of the table above has items from this machine,
quoting what was read; drift raises at least one real gap of a kind step 2 could not see and it is decided;
`scripts/trace.sh` follows a route to the container that serves it.
