# Substrate's parts and the default distribution (S-211, S-212)

Substrate is the home of the kernel's **optional modules** and of the **default distribution** that includes them.
The kernel's core ships without them (knowledge, review, authentication, the module contract, the record); a
person who wants only the kernel never installs them. Our agents and experiments are built on the default
distribution. **A part is a kernel module only when it needs the kernel** (its own role, its data in the kernel's database, the
review lane; S-213), written to the kernel's module contract (S-203) and shipped from this repository. Otherwise it
is the standard type it already is: an Agent Skill, an MCP server, a compose service, a harness plugin, or an external
service in the default collection. Nothing has been rebuilt yet.

## Substrate's optional parts (shipped from here, not with the kernel's core)

| Part | Where it is now | What it becomes |
| --- | --- | --- |
| The live environment: signals, a queue per actuator, gates, the record | `environment/sql/`, `environment/db.py` | a kernel module (it needs the kernel's database and review lane): its gates send `propose` to the review lane, so a person approves in one place |
| The channel into a harness session | `environment/channel.py` | an MCP server a harness connects to, reading the environment module's queues |
| The MCP router: one endpoint, each tool an action behind its gate | `mcp-router/` (Go), `environment/sql/010_mcp.sql` | an MCP server run as a compose service, its registry in the environment module's schema |
| The desktop: windows, the launcher, framed apps | the kernel's shell (`modules/ui`, the kernel's D-127); `deploy/caddy/` | stays the kernel's, in its repository, growing there by its pull requests as use cases need (S-214); Substrate's views install onto it |
| The assistant's conversation | `desktop/`, `environment/sql/011_desktop.sql` | a view module from this repository, installed into the kernel's desktop; its messages kept in the environment module |
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
2. Substrate's parts in their types, in this repository: the environment as a kernel module, the channel and the
   router as MCP servers on it; the assistant's conversation as a view installed into the kernel's desktop, built as far as a use case needs.
3. The default distribution: the compose file installs the kernel's core and Substrate's modules, the harness is
   configured to use them, `scripts/check.sh` checks the wiring.
4. The test of the bet (S-211 c): one implementation project on a demo SMB, end to end.
