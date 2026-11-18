# Direction: experiment first

Set on 2026-11-14 (S-94). It supersedes S-41's scope and pauses `docs/build.yaml`. `docs/spec.md` stays as the
record of what was built and why; where the two disagree, this file wins until the spec is rewritten.

## Three principles

1. **Know yourself before changing yourself.** The map.
2. **Know your options before deciding.** The catalogs.
3. **Prove a change before keeping it.** The judge.

Every part of this repository should trace back to one of them. Anything else is either a way to do one of the
three or a candidate being tested.

## Three projects

| Project | Is | Stays out of |
| --- | --- | --- |
| **Knowledge Kernel** (today `workbench/`; the old kernel repository will host it) | a knowledge base where every write has a claim: content types, claims beside every value, taxonomies, ontologies, mappings, views | judging, optimizers, held-out data, any cognitive architecture |
| **Morphogen** | a CI/CD agent for governed components: it searches, judges and lands changes, and is kept as external as possible | maps, catalogs, any knowledge of the Knowledge Kernel |
| **Substrate** (this repository) | the starter culture: candidate architectures, catalogs, domains, environments, deployment, Claude Code's skills | framework code |

Cognitive architectures are candidates, not framework. The handlers ladder is now called the **fallback
learner**: dearer tiers handle what cheaper ones cannot, then compile what they worked out into something cheaper.
It is a hypothesis to test, like any other.

## Floor and seed

**Floor**, changed only by people: the provenance of every write, the record of calls and outcomes, the judge
(custody of held-out cases, the meter, the statistics, the evidence log), and who may approve what.
**Seed**, meant to be beaten: everything else, the fallback learner and the claims' epistemics included.

State (claims, memories, outcomes) is written freely. Structure (anything that changes how a component behaves)
lands only on a verdict and its approval.

## What research is aimed at

Work businesses already pay AI to do, where the outcome can be checked: customer support, back-office and document
work, coding. Every role is measured as **value per dollar**: real work completed at acceptable quality, against
what it cost to run. An **environment** is what one kind of work senses and may do (its sensors and their encoders, its actions
and their gate, the outcome measure) behind the reset-and-step interface, so a benchmark and a live deployment
of the same work look alike; an **agent** is the handlers that act in it, a model being optional; a
**package** holds both and is what is started and shared (S-102, `docs/contracts/environment.md`).

## Plan

| # | Step | Done when |
| --- | --- | --- |
| 0 | Settle and freeze | the SessionStart hook names no build step; S-94 is recorded (done with this file) |
| 1 | Pick the first environment: support or back-office work, through the `research` skill, with the budget arithmetic first (calls per judged run against the free tier's 1,000 a day and what the local model can carry) | `docs/choices/first-environment.yaml` records the pick, its trial and its budget |
| 2 | Wire the environment and a plain-agent baseline | the baseline runs end to end, every model call counted at the gateway |
| 3 | Check that the judge can see: the baseline against itself, then a deliberately worse candidate against it | the same-candidate run shows no difference; the worse candidate is refused |
| 4 | The first comparison: the plain agent against the same agent with one compile-down step | a verdict with its trade-offs, recorded |
| 5 | The cheat log: proposers run against the judge on that environment, every refusal kept with what was tried | about a dozen real entries, and at least one honest improvement that passed |
| 6 | Launch on the cheat log and the judged improvement, with an invitation to break the judge | published |
| 7 | The replication series: papers on agent architectures re-run at equal budget, volunteers running the screening | the first replication record is published |

## Backlog: built when an experiment needs it, not before

- the rename pass (Knowledge Kernel, fallback learner, taxonomy beside ontology, moderation queue, workflow);
- thinning Morphogen: optimizers as plugins, a materializer interface, the meter as its own observer;
- splitting the Knowledge Kernel's core (provenance fixed, epistemics a plugin) and moving it to the kernel repository;
- a gate service, an OS user and database role per role, versioned governed tables (git gates the one governed
  component that exists);
- a registry of encoders, processors and decoders; SKOS taxonomies; nanopublications as the export format for claims;
- maps as views, once a view can regenerate `catalog-info.yaml` exactly;
- a Soar-based candidate; judging many candidates at once; volunteered compute; the business track.

## Not yet verified

The old kernel repository has not been read since it was retired (S-68). The benchmarks shortlisted for step 1
(policy-bound support simulations, OmegaUse-OfficeVal, TheAgentCompany) have not had their licences, upkeep or
run costs checked. Step 1 checks each before anything rests on it.
