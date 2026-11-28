# Substrate's parts and the default distribution (S-211, S-212)

Substrate is the home of the kernel's **optional modules** and of the **default distribution** that includes them.
The kernel's core ships without them (knowledge, review, authentication, the module contract, the record); a
person who wants only the kernel never installs them. Our agents and experiments are built on the default
distribution. **A part is a kernel module only when it needs the kernel** (its own role, its data in the kernel's database, the
review lane; S-213), written to the kernel's module contract (S-203) and shipped from this repository. Otherwise it
is the standard type it already is: an Agent Skill, an MCP server, a compose service, a harness plugin, or an external
service in the default collection. The environment, the channel and the router are in their types since 2026-11-27
(S-219 to S-221).

## Substrate's optional parts (shipped from here, not with the kernel's core)

| Part | Where it is | What it is |
| --- | --- | --- |
| The live environment: signals, a queue per actuator, gates, the record | `environment/` (`module.yaml`, `migration.sql`, the schema in `sql/` by `db.py`, the service `review.py`, compose `environment`) | **done (S-219):** a kernel module, installed by `kk module install` (`scripts/kernel.sh init`); a proposed action waits in the kernel's review lane, so a person approves in one place, the desktop's Review, and the module records that decision on the action |
| The channel into a harness session | `environment/channel.py` | **done (S-220):** an MCP server (stdio) a harness starts, reading the environment module's queues as its own login (`mcp_channel`, role `env_agent`) |
| The MCP router: one endpoint, each tool an action behind its gate | `mcp-router/` (Go), compose `mcp-router` and a connector per server; its registry `environment/sql/010_mcp.sql` to `013` | **done (S-220):** an MCP server run as a compose service, its registry and gates in the environment module's schema; it decides nothing (S-219) |
| The desktop: windows, the launcher, framed apps | the kernel's shell (`modules/ui`, the kernel's D-127); `deploy/caddy/` | stays the kernel's, in its repository, growing there by its pull requests as use cases need (S-214); Substrate's views install onto it |
| The assistant's conversation | `desktop/` (the view `view-assistant`, mounted into the kernel's container; its server an MCP server through the router), `environment/sql/011_desktop.sql` | **in its type already (S-221):** a view module from this repository in the kernel's desktop, its messages signals in the environment module; built further when a use case asks |
| Substrate's read model and encoder | the kernel's `view-substrate`, `encoder-substrate` | brought here as Substrate's modules, or retired once maps are items (S-207) |
| The old store UI | `ui/` | retired once the kernel's views and the map viewer (S-207) do its job; kept until then (S-221) |

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
or a module on top of the default one. The manager agent (S-223, proposed; `docs/manager-agent.md`) is one: a session on the
channel and the router, the portfolio's tables in the environment module, a supervisor service and a view module.

## Order

1. Morphogen's kit (`docs/morphogen-kit.md`), by pull request there.
2. **Done 2026-11-27 (S-219 to S-221) but for what waits on use cases:** Substrate's parts in their types, in this repository: the environment as a kernel module, the channel and the
   router as MCP servers on it; the assistant's conversation as a view installed into the kernel's desktop, built as far as a use case needs.
   Left: Substrate's read model and encoder (the kernel's `view-substrate`, `encoder-substrate`) and `ui/`, both waiting on S-207 (maps as items).
3. The default distribution: the compose file installs the kernel's core and Substrate's modules, the harness is
   configured to use them, `scripts/check.sh` checks the wiring.
4. The test of the bet (S-211 c): one implementation project on a demo SMB, end to end.
