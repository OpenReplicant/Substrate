# Plan

Substrate is the seed (`docs/seed.md`, S-155, S-162). Its first target is MetaSoar (`OpenReplicant/MetaSoar`):
the original Soar with Substrate on its impasses (S-160, S-161). The plans before S-155, and the framework they
built, are at the tag `framework-final`.

| # | Step | Done when |
| --- | --- | --- |
| A | The seed's spec and decisions (S-154 to S-162) | merged by the owner |
| C | The map format and Substrate's map of itself, with the evidence check | done 2026-11-18 (S-162): `catalog-info.yaml`, 26 entities in `map/`, `check.py` passes and reports a changed source as stale |
| D | Distil the tree to the seed | done 2026-11-18 (S-162): the framework tagged `framework-final` and removed; the stack stopped, its volumes kept |
| E | Morphogen on Substrate: a `morphogen.yaml` whose first cell is the check and the skills, and its check required on `main` | a pull request to Substrate gets Morphogen's verdict as a required check (waits on the owner's GitHub App) |
| F | The plugin: the skills packaged for Claude Code, installed from GitHub into a fresh session | it maps a repository it has never seen and opens a judged pull request |
| G | MetaSoar step 2: the environment interface and the first grid game picked (`research`); the adapter | the starting rules play an episode through the adapter |
| H | MetaSoar step 3: the hook, calling Substrate on an unresolved impasse | an impasse comes back as a judged, gated change to the agent's rules, and the next episode plays better |
| I | The MCP server (`map/blueprint/`): `improve`, `status`, `explain`, `revert` | an agent asks for an improvement and a gated pull request comes back |

## The owner's to decide

- MetaSoar's licence (public, none chosen yet; Apache-2.0 recommended, to match Substrate and Morphogen).
- Registering Morphogen's GitHub App (step E).
- Which comes first as a business (Morphogen's hosted judge, Substrate's mapping as a service, the MetaSoar
  write-up), and when each repository goes public.
