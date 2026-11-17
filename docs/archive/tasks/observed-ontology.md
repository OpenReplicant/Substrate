# Task: nothing observed is dropped: anything observed is a component or an interface, nested

**Model:** Opus, against the design below. **Needs:** nothing.
From `docs/readiness.md`, walk 2: finding 2.1 (and 2.2, 2.4). Owner, 2026-11-15: "we ran into the gap of needing
ontologies to represent findings and make sure they get used".

## The problem

Each kind of thing Substrate can observe is a hand-written content type with its own extractor code (`host`,
`container`, `route`, ...). A client's machine has things outside that list (services, timers, ports, disks,
a GPU, a second container engine), and those are collected and silently dropped. Adding a type per kind by
hand does not scale to systems nobody here has seen, and repeats what S-86 decided against for businesses:
inventing where adopting would do.

## Scope

The owner, in the same interview: "the concept of 'system mapping' really applies to anything that can be
learned as a collection of components/interfaces, recursively all the way down... we don't need much ontology
for that, but there are diverse approaches depending on what you're looking at or from what zoom-level". So
the core stays small, and ontologies are lenses laid over it, not a precondition.

1. **Nothing is dropped.** Every snapshot the collector writes is accounted for. The extractor's log says how
   many snapshots it read and how many it made nothing from.
2. **The generic form is a component or an interface, nested.** What has no type of its own becomes an
   observed component (a thing that runs or holds something: a service, a disk, a GPU, a container engine) or
   an observed interface (where things meet: a listening port, a mount, a socket), with a free-text `kind`,
   its parent (`rig` contains Docker, Docker contains the speech container, which provides port 8880) and the
   data read, citing the snapshot. That is the map's own shape and Morphogen's (cells in a containment tree,
   interfaces joining them), so drift, `trace.sh` and the Map view work on it at any depth without new code
   per kind. Which of the two a kind is, and what its parent is, is data in `observe.yaml` beside the command
   that reads it.
3. **Zoom is a view.** A map is read at a level: the machine, one engine, one container. Nothing is stored per
   level; a view shows a component with its children folded or open.
4. **Ontologies are optional lenses.** A class from an adopted ontology is a mapping onto a `kind`, added when
   a domain needs to say more than "component" (as the business plugin does, S-86), chosen through the
   `research` skill at that point. No ontology is picked in this task. A `kind` with no class is not a gap.

## Files to touch

`plugins/substrate/substrate_plugin.py` (the `observed` and `drift` extractors), `plugins/substrate/observe.py`
(`engine` as a list, finding 2.2; text output kept as lines, 2.4), `observe.yaml` (the form a command's output
takes), `plugins/substrate/types/` (one type for an observed component and one for an observed interface, or
the existing ones widened: say which and why), `plugins/substrate/OBSERVE.md`, `plugins/substrate/MAP.md`
(zoom), tests in `plugins/substrate/tests/test_observe.py` and `test_drift.py`, then
`plugins/substrate/vocab.py` to regenerate, `DECISIONS.md` (one row).

## Leave alone

`workbench/` (it already holds classes, properties and mappings for any plugin). The collector's rule that
values which may be secret are never written. The existing observed types' fields and slugs (their items have
claims and decisions). `repos/`.

## Done when

On this machine, with the owner's `observe.local.yaml`: every snapshot is accounted for in the extractor's
log; the services, the second container engine and its container, the listening ports, the disks and the GPU
are items citing their snapshots, each with a parent; `scripts/trace.sh` follows port 8880 to the container
that provides it and up to `rig`; adding a new kind needed a change to `observe.yaml` only;
`scripts/test.sh` and `scripts/check.sh` pass.
