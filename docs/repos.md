# The repositories and what each owns

The shape is `docs/framework.md` (S-209 to S-214). Every dependency between them is a contract (Backstage entity
files, MCP, Agent Skills, OpenEnv, Morphogen's cells, an OpenAI- or Anthropic-compatible model endpoint, the
kernel's module contract), never another project's code.

| Repository | Owns | Depends on |
| --- | --- | --- |
| **Morphogen** (OpenReplicant/Morphogen) | The kit: map, research, catalog and optimise, on files only. Its skills (`map`, `catalog`, `research`, `morphogen`), its file formats (Backstage entities with `spec.morphogen`; the operator's private file), the judge, its optimiser adapters, the evidence log; a core Python package, Agent Skills, a Claude Code plugin. Changes by pull request there | files; any harness that takes Agent Skills and MCP |
| **Kernel** (OpenReplicant/kernel) | Postgres made into a kernel. Its core: knowledge (claims with provenance, belief and clearance; review; recall), authentication, the module contract, the record, and its desktop (the shell with windows, launcher and framed apps). Its modules, including `encoder-backstage`, which ingests Morphogen's files. Its own distributions folder (`business`, `devops`, `papers`, `process-maps`). Its Substrate-specific modules (`encoder-substrate`, `view-substrate`, kernel-mcp's `substrate` profile) are retired together once Morphogen's skills replace Substrate's | Postgres |
| **Substrate** (this one) | The default distribution: the harness's configuration, its optional parts installed onto the kernel (the environment and gates, the channel, the MCP router, the assistant's view), the stack (compose, the gateway, local models, the tools container, scripts), the `setup` and `upstream` skills, `distributions/`, and this documentation | the kernel, Morphogen, Bifrost and Claude Code as default fillers, through their contracts |
| **MetaSoar** (OpenReplicant/MetaSoar) | The research: cognitive architecture (impasse-driven compilation, M-17), System 1 skills (M-19), its experiments on OpenEnv, atlas and the Soar 9.6.5 baseline | OpenEnv; Morphogen to judge |

envkit, the in-process scheduler MetaSoar's worlds ran on, was retired from Substrate in S-196: environments are
OpenEnv environments (S-184).
