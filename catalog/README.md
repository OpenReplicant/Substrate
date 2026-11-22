# Substrate's catalog

Substrate's own parts, one file per entity, in **Backstage's entity format** (`backstage.io/v1alpha1`): components
(services, jobs, agents, blocks, plans, external services), the APIs they provide and consume, the database, the
system and its owner (S-176). It is the first content type of the kernel's D-101: each entity is an item, each file a
version kept as an artifact, and the kernel's claims about it (each citing its file and line) are its fields.

- **Interfaces** are `API` entities: `spec.type` names the protocol (`openapi`, `asyncapi` for a pgmq queue, `mcp`,
  `websocket`, `http`, `wot-td` for blocks and plans) and `spec.definition` holds the contract; a block's is a
  WoT Thing Description action read from its `block.yaml`.
- **Annotations** (`substrate.dev/*`): `licence`, `image`, `compose-service`, `decision`, `source`, `gate`,
  `otel-service`, `trigger`.
- **A queue's provider** is the component that receives on it (the worker provides `worker-tasks`; the voice head
  and the UI consume it by publishing to it), as in AsyncAPI.

```sh
bin/in-tools python3 scripts/catalog.py check --compose deploy/compose.yaml   # every consumed API provided, compose matched
bin/in-tools python3 scripts/catalog.py apis                                  # each API, its providers and consumers
scripts/kernel.sh catalog                                                     # into the kernel (encoder-backstage)
bin/in-tools python3 scripts/catalog.py check --kernel                        # the same fit from the kernel's claims, and drift
```

`scripts/check.sh` runs the first; a compose service added without an entry fails it.
