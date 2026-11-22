# The repositories and what each owns

| Repository | Owns |
| --- | --- |
| **Kernel** (OpenReplicant/kernel) | The store: claims with provenance, belief and clearance; review; recall; the memory profile (MCP); the business distributions (its D-84, D-115). |
| **Substrate** (this one) | The framework: environments (`environment/` on pgmq, and `envkit/`), the model gateway, gates, the companion, the voice head and avatar, the UI, the catalog, components and the judge. |
| **MetaSoar** | Research: the cognitive hypothesis (headline: impasse-driven compilation, M-17), atlas, the experiments, and the Soar 9.6.5 baseline. |
| **Morphogen** | The judge of MetaSoar's pull requests. Out of Substrate's build while the owner refactors it (rule 9). |

## Dependencies

MetaSoar -> Substrate -> Kernel. MetaSoar runs its experiments in Substrate's environments (envkit, S-161); Substrate keeps and reads its knowledge in the Kernel. Morphogen sits beside the chain and judges MetaSoar's pull requests; nothing imports it.

Until MetaSoar depends on Substrate's copy of `envkit/`, its `atlas/cartographer.py` and `atlas/mover.py` import `envkit`, and `envkit/run.py` imports `atlas`.
