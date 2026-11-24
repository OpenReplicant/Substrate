# Substrate's parts and the default distribution (S-211, S-212)

Substrate is the home of the kernel's **optional modules** and of the **default distribution** that includes them.
The kernel's core ships without them (knowledge, review, authentication, the module contract, the record); a
person who wants only the kernel never installs them. Our agents and experiments are built on the default
distribution. Every part is either a **kernel module** written to the kernel's module contract (a manifest, its
code, its own role, run on its own; S-203) and shipped from this repository, or a **standard module type** (a
compose service, an MCP server, an Agent Skill, a harness plugin). Nothing has been rebuilt as a module yet.

## Substrate's modules (optional kernel modules, shipped from here)

| Module | Where it is now | What it becomes |
| --- | --- | --- |
| The live environment: signals, a queue per actuator, gates, the record | `environment/sql/`, `environment/db.py` | a module whose gates send `propose` to the kernel's review lane, so a person approves in one place |
| The channel into a harness session | `environment/channel.py` | part of the environment module: an MCP server a harness connects to |
| The MCP router: one endpoint, each tool an action behind its gate | `mcp-router/` (Go), `environment/sql/010_mcp.sql` | a module of its own (a kept service), its registry in the environment module's schema |
| The desktop: windows, the launcher, framed apps | the kernel's shell (`modules/ui`, the kernel's D-127); `deploy/caddy/` | a module, if the kernel agrees to move its window manager out of its core shell (the kernel's decision, by its pull request) |
| The assistant's conversation | `desktop/`, `environment/sql/011_desktop.sql` | a view module in the desktop, its server folded into the environment module |
| Substrate's read model and encoder | the kernel's `view-substrate`, `encoder-substrate` | brought here as Substrate's modules, or retired once maps are items (S-207) |
| The old store UI | `ui/` | retired: the kernel's views and the map viewer (S-207) do its job |

## The default distribution

| Part | Where it is now | Type |
| --- | --- | --- |
| The kernel's core | the kernel's image | the kernel |
| Substrate's modules | above | kernel modules |
| Morphogen | its Claude Code plugin | a harness plugin; the map, catalog and research skills move into it (S-209) |
| The harness, configured | `.claude/settings.json`, hooks, the MCP servers it connects to | Claude Code first (the Anthropic subscription); OpenHands a candidate |
| The model gateway (Bifrost) | compose service `gateway`, `scripts/gateway.py` | a compose service, configured |
| Local models (Ollama, llama.cpp `llm`, `llm-fast`) | compose services | compose services |
| The Postgres image (pgvector, pgmq, pg_cron, pgGraph) | `deploy/postgres/` | the kernel's image, if the kernel needs the same extensions; else a compose service |
| The tools container | `deploy/tools/`, `bin/` | a compose service, while scripts need it |
| The setup and upstream skills | `.claude/skills/` | Agent Skills about this repository |
| Bringing it up | `deploy/compose.yaml`, `scripts/` (`up`, `down`, `check`, `test`; the runtime's four verbs in `scripts/lib.sh`) | the distribution's own |
| Substrate's own map | `catalog/` | Backstage entity files in Morphogen's format (S-209): Substrate mapped like any project |

## Built on it

The assistant, MetaSoar's experiments, the games and embodied environments: each a distribution (`distributions/`)
or a module on top of the default one.

## Order

1. Morphogen's kit (`docs/morphogen-kit.md`), by pull request there.
2. Substrate's parts rebuilt as kernel modules, in this repository: the environment and channel, the router, the
   assistant's conversation; the desktop when the kernel has decided where its window manager lives.
3. The default distribution: the compose file installs the kernel's core and Substrate's modules, the harness is
   configured to use them, `scripts/check.sh` checks the wiring.
4. The test of the bet (S-211 c): one implementation project on a demo SMB, end to end.
