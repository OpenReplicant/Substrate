# The repositories and what each owns

| Repository | Owns |
| --- | --- |
| **Kernel** (OpenReplicant/kernel) | The store: claims with provenance, belief and clearance; review; recall; the memory profile (MCP); the business distributions (its D-84, D-115). |
| **Substrate** (this one) | Everything that runs: environments (`environment/` on pgmq, and `envkit/`), the model gateway and the gate in front of it, the assistant and its voice front end and avatar, the UI, the catalog, components and the judge, and the experiments (`experiments/`, from MetaSoar, S-181). |
| **MetaSoar** | Research: the cognitive hypothesis (headline: impasse-driven compilation, M-17) and its write-up. Its experiments move into Substrate's `experiments/` (S-181), as envkit did; atlas and the Soar 9.6.5 baseline move when an experiment needs them. Its repository is changed by its own commits. |
| **Morphogen** | The judge of MetaSoar's pull requests. Out of Substrate's build while the owner refactors it (rule 9). |

## Dependencies

Two products: the Kernel (the store) and Substrate (everything that runs), Substrate -> Kernel: Substrate keeps and reads its knowledge in the Kernel. MetaSoar is the research write-up; its experiments run in Substrate (S-181). Morphogen sits beside the chain and judges MetaSoar's pull requests; nothing imports it.

Until MetaSoar depends on Substrate's copy of `envkit/`, its `atlas/cartographer.py` and `atlas/mover.py` import `envkit`, and `envkit/run.py` imports `atlas`.
