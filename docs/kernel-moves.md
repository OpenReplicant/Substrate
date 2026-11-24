# Where each part of Substrate goes (S-211)

Substrate becomes a default configuration: a harness set up to use the kernel and Morphogen. Every part of the tree
today is either a **kernel module** (the kernel's module contract: a manifest, its code, its own role, run on its
own; S-203) or a **standard module type** (a compose service, an MCP server, an Agent Skill, a harness plugin), or it
stays as the configuration itself. The kernel's side changes by its own pull requests (the owner's). Nothing has
moved yet.

## Into the kernel, as modules

| Part | Where it is now | As a kernel module |
| --- | --- | --- |
| The live environment: signals, a queue per actuator, gates, the record (`env` schema) | `environment/sql/`, `environment/db.py` | the interaction module the kernel's own standards name (objects, gated actions, events, queues); its gates send `propose` to the kernel's review lane, so a person approves in one place |
| The channel into a harness session | `environment/channel.py` | part of the same module: an MCP server a harness connects to |
| The MCP router: one endpoint, each tool an action behind its gate | `mcp-router/` (Go), `environment/sql/010_mcp.sql` | a module of its own (a kept service), its registry in the interaction module's schema |
| The desktop's conversation and the Assistant window | `desktop/`, `environment/sql/011_desktop.sql` | a view module in the kernel's shell, as the Assistant view already is; its server folded into the interaction module or the router |
| The front door and framed apps | `deploy/caddy/` | the kernel's deployment (its UI shell is already behind it, the kernel's D-127) |
| Substrate's read model and encoder | already the kernel's `view-substrate` and `encoder-substrate` | renamed for what they do, or retired once maps are items (S-207) |
| The old store UI | `ui/` | retired: the kernel's views and the map viewer (S-207) do its job |

## Standard module types, kept as configuration

| Part | Where it is now | Type |
| --- | --- | --- |
| The model gateway (Bifrost) and its config | compose service `gateway`, `scripts/gateway.py` | a compose service, configured |
| Local models (Ollama, llama.cpp `llm`, `llm-fast`) | compose services | compose services |
| The Postgres image (pgvector, pgmq, pg_cron, pgGraph) | `deploy/postgres/` | the kernel's image, if the kernel needs the same extensions; else a compose service |
| The tools container | `deploy/tools/`, `bin/` | a compose service, while scripts need it |
| Morphogen | its Claude Code plugin | a harness plugin |
| The map, catalog and research skills | `.claude/skills/` | Agent Skills, moving into Morphogen (S-209) |
| The setup and upstream skills | `.claude/skills/` | Agent Skills, staying here: they are about this configuration |
| Substrate's own map | `catalog/` | Backstage entity files in Morphogen's format (S-209): Substrate mapped like any project |

## What stays as Substrate

The harness's configuration (`.claude/settings.json`, hooks, the MCP servers it connects to, Morphogen's plugin
pinned), the compose file that brings the stack up, `scripts/` (up, down, check, test, the runtime's four verbs in
`scripts/lib.sh`), `repos.yaml`, `DECISIONS.md` and the docs. `distributions/` stays here until a distribution
needs a home of its own.

## Order

1. Morphogen's kit (`docs/morphogen-kit.md`), by pull request there.
2. The interaction module in the kernel (environment, channel, router), with its gates on the review lane.
3. The desktop's conversation as a kernel view module.
4. Substrate cut to its configuration: what moved is removed here, the compose file pulls the kernel's modules, and
   `scripts/check.sh` checks the wiring.
5. The test of the bet (S-211 c): one implementation project on a demo SMB, end to end.
