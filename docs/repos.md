# The repositories and what each owns

The layers are in `docs/framework.md` (S-185). Every dependency between them is a contract (OpenEnv, MCP, Backstage
entity files, Morphogen's cell file, an OpenAI- or Anthropic-compatible model endpoint), never another project's code.

| Repository | Owns | Depends on |
| --- | --- | --- |
| **Kernel** (OpenReplicant/kernel) | Postgres made into a kernel: knowledge (claims with provenance, belief and clearance; review; recall; the memory and `substrate` MCP profiles), interaction (objects, gated actions, events, queues: the `env` schema moves into its database, S-190), authentication, pluggability; its modules are data transformations and what happens at the Postgres level; its own distributions folder (`business`, `devops`, `papers`, `process-maps`) | Postgres |
| **Substrate** (this one) | The orchestrator kit: skills (`map`, `catalog`, `research`, `orchestrate`, `optimize`, `setup`, `upstream`), hooks, the channel, the catalog (`catalog/`), the adapters (OpenEnv, the model proxy, compose decoding), the reference stack (compose, the gateway, the tools container, scripts), this documentation; and, until Substrate's shape is settled, the distributions as folders (`distributions/`) | the contracts; the Kernel, Morphogen, Bifrost and Claude Code as default fillers |
| **Morphogen** (OpenReplicant/Morphogen) | The optimiser: cells, optimizers behind a judge they cannot edit, the still-works gate, the system guard, the evidence log; shipped as a Claude Code plugin with an MCP server. Its own repository on purpose: the judge's independence from what the optimizer edits is the point. Changes by pull request there | cell files; reads Backstage entities when present |
| **MetaSoar** (OpenReplicant/MetaSoar) | The research: cognitive architecture (impasse-driven compilation, M-17; System 1 from experience), its experiments on OpenEnv, atlas and the Soar 9.6.5 baseline | OpenEnv; the assistant distribution's ladder for M-17 |

Until MetaSoar's worlds are OpenEnv environments (S-184), its `atlas/cartographer.py` and `atlas/mover.py` import
Substrate's `envkit`, and `envkit/run.py` imports `atlas`, so the two must be on one path.
