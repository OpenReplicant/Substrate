# Substrate

An agent framework. You put an environment on a system you need, run it, and watch and change it. With nothing
else configured, every event in the environment goes to an LLM harness (Claude Code), which acts through gated
actuators, and everything is recorded. From that record, components are distilled that handle what repeats; each
carries a card and is judged on cases its author never saw before it joins.

The first environment is **the companion**: a persistent assistant that you talk to, that works in the
background, and that manages its own model and compute budget (later with a voice, an avatar, and mixed reality
on a Quest 3).

- `docs/plan.md`: what is built next, step by step
- `docs/framework.md`: the shape: signals and claims, the store, pass-through, components and cards, the judge,
  nesting
- `docs/privacy.md`: the rules for personal streams, with their defaults
- `DECISIONS.md`: every default and why, append-only

## The store

Wikibase's data model in Postgres, with graph and vector features (S-135). Entities have statements; a
statement is a property, a typed value, qualifiers, a rank (preferred, normal, deprecated) and references saying
who stated it and which span of which source it rests on. Spans carry a hash, so when a source changes, what
cites it is flagged without a model call (after OpenWiki). An interpreter's statement (a model's, a person's)
is a claim: it enters at normal rank and review prefers or deprecates it. Graph queries, SPARQL and vector search
are views over the same tables.

## Running it

Needs git, python3, Podman with compose, and Claude Code; everything else runs in containers.

```sh
scripts/bootstrap.sh   # once: images and the tools container
scripts/up.sh          # the stack and its databases, then the checks
scripts/check.sh
```

This is the fresh tree (S-137). v1, a store with a claim behind every value, a map of the system, and the
Morphogen judge in the build, is tagged `v1-final`.

## Licence

See `LICENSE`.
