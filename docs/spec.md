# Substrate spec

What substrate is meant to become. **While this file is in place, Claude Code sessions in this repository build
it out**, one step of the build plan (section 9, tracked in [`build.yaml`](build.yaml)) at a time, with the
`build-out` skill; each step ends with its check passing, and decisions that are the owner's wait for the owner.
Delete this file (or set a step's status to `dropped`) to stop that. The previous spec ("a mind in an
organism") is in git at `a00fb61`; this one replaces it (S-41).

## 1. What substrate is

A self-modifying agent platform: an agent in charge of a system of components, and its own system is one of
them. It models each system as cited claims, acts on that model, and changes something (itself included) only
on evidence it cannot fake.

**Components are the unit.** A component is anything that can be modified: a service, a library, a skill, a
hook, a parameter, a prompt, a vocabulary, a process step. Backstage's entity model (kinds such as Component,
Resource, API, System, and a free `type` on each) covers all of them, which is why the catalog uses it. That
is the level at which substrate understands what it learns, at least structurally: what the parts are, what
each is for, what depends on what, and what may change. Morphogen reads the same catalog as cells, so whatever
can be named as a component can be judged as one.

**Self is not a special case.** Substrate models itself exactly as it models any other system: its own project
in Workbench, its own catalog, the same extractors, drift checks and judge. Nothing in the loop works only on itself.
That is what makes it self-modifying, and what makes several systems in one world model ordinary: each is a
project, and the relations between them (this one manages that one; this component calls that API) are claims
like any other.

The same loop, pointed at widening targets, gives three levels:

| Level | It models | Which makes it | Proven when |
| --- | --- | --- | --- |
| **Autopoietic** | itself: its components (services, skills, hooks, parameters) and its map | self-modifying | a gap in its own model is found, a change closing it is judged, and the verdict lands as claims (step 2), with the observed half covering what actually runs it (step 5) |
| **Engineer** | another system beside itself, from observation, exploration and interviews | able to manage what it models | both systems are in one world model, and one judged change is made to the other (step 8: the machine substrate runs on) |
| **Generalist** | anything that can be described as components, by growing what a domain needs: content types, vocabularies, encoders, code, views | adaptable | a direction, not a build step: where Workbench's content model points |

Each level depends on the one before. Self first, because the system is right here and every claim can be
checked. Engineer is the same loop aimed at a second system, with the first still in view. Generalist is
where the foundation leads: a new domain may bring code and a view of its own, but it should not need a new
store, a new judge or a different loop. Managing systems of components is the scope; going further is left
open (S-49).

**Direction: from asking a model to knowing (S-61).** The owner's aim beyond the scope: once substrate knows
itself and can adapt, it should learn, reason and act in general, with a range of learning methods to choose
from as components (an AutoML catalog), tested on video games and on internet research. The path there is to
distil what the language model does slowly into faster, checkable parts. Rules are the first: an OWL 2 RL
reasoner applies them over claims (step 7), then rules are learned and judged (section 8, held ideas), then
learned models. Each is a component like any other: chosen from a catalog, judged by Morphogen against what
runs now, and kept only on evidence. Nothing in the build plan depends on it yet.

## 2. How it works: science-minded

Substrate works the way a careful scientist does.

- **Claims are observations and hypotheses**, never facts by assertion. Each is attributed, quotes its
  evidence and carries a belief that support and contradiction move.
- **A change is an experiment.** It states what it should improve and how that will be measured, before it is
  run. It is then tested against what runs now, on cases the changer has not seen.
- **Negative results are results.** A rejected candidate, a dropped step or a change that did not help is
  recorded with its evidence, so it is not tried blind again.
- **Noise is measured.** Morphogen's A/A checks (the same candidate judged twice) put a number on how much a
  verdict wobbles, so wobble is not mistaken for improvement.
- **Choices come from catalogs, not best guesses** (section 5): look for candidates, test the shortlist,
  record why one was picked.

**The design is open; the judge is not.** Architecture, code, content types, views and parts can all change,
and new ones can be added whenever a step needs them. The one hard restriction is Morphogen. Substrate is
expected to try to reward-hack sometimes: to pass a check by weakening it, to measure what is easy instead of
what matters, or to tune on the test set. That is an ordinary pressure on any optimiser, not a failure of
character. Morphogen is built so the changer cannot reach the rules, the measurement or the held-out cases,
and its red team looks for exactly these moves first. Everything else stays adaptable.

## 3. The loop

```
observe ─▶ claim ─▶ model ─▶ gap ─▶ propose ─▶ judge ─▶ apply ─▶ (observe)
  encoders,   cited,    graph of    intended    builder,     Morphogen   branch, PR,
  explorer,   typed by  the system  vs          optimizer,   verdict     config, a
  interviews  ontology  (catalog)   observed    response                 notice
```

**Two halves of a model.** Every model has an intended half (what the system is meant to be: declared parts,
owners, relations, process, stated by people) and an observed half (what it actually is: what runs, what calls
what, what happened, measured by encoders). Both are claims in one store, so they can be compared. The gap
between them is where all of substrate's work comes from.

**A gap closes either way.** Practice can be brought back to intent (a fix), or intent revised to match
practice that turned out better. Which way is a decision, made in Workbench's review lane with the evidence beside
it. Always enforcing the blueprint makes a system rigid; always accepting what it observes leaves it no
identity.

**Organization and structure.** What makes the system itself (purpose, goals, policy, who decides) changes
only through the owner. What currently realises it (code, config, skills, parts, the map) changes whenever a
verdict says the change fits better.

**Architecture is content.** Substrate's own parts are entries in its own catalog. Changing its architecture is
the same operation as changing anything else it models: propose an edit to the map and to what realises it,
get it judged, and record the result as claims.

## 4. Parts

Three, plus the glue between them.

| Part | Does | Where |
| --- | --- | --- |
| **Workbench** | the store and the model: a content system on Postgres, typed items with claims beside every value; its shell, API, server and MCP | `workbench/` (built to leave) |
| **Claude Code** | the actor: explores, interviews, researches, builds, maps; its skills are substrate's procedures | you |
| **Morphogen** | the judge: a change lands only with a verdict the changer cannot reach | `repos/morphogen` |

The glue is this repository: scripts that bring the parts up and connect them, the tools container they run in
(S-19), substrate's Workbench plugin (`plugins/substrate`), and the map (`catalog-info.yaml`). It runs one way for
now: compose with Podman, secrets in `.env`.

### The store: Workbench

Workbench (`workbench/BRIEF.md`) is a general-purpose, AI-first content system on Postgres, and substrate is one
plugin on it (S-52 to S-57). It keeps what kernel, its predecessor, was for and drops what got in the way: claims,
structure and ontologies sit together at the centre, and everything that works on them is a plugin around it.
Ontologies serve as taxonomies; extraction, comparison and graph projection are plugins and queries.

- **Content types are tables** with real columns, registered by plugins from JSON Schema; **items** are rows.
- **Claims are the evidence layer** beside them: every value an item has, a claim says who or what stated it,
  from which source, quoting it, when. Triggers in Postgres record them for every write, by a person, an agent
  or an extractor alike; an edit supersedes its author's earlier claim, and other sources stay beside it.
- **Vocabularies and SSSOM mappings are tables**: a domain keeps its own terms, and mappings relate them (S-33).
- **System graphs use the catalog's entity model**, in Backstage's names, as items and relations; no Backstage
  server (S-38). A catalog can hold any kind of thing: a service, a package, a skill, a verdict.
- **Postgres does the rest**: row-level security, full-text search (recall), pgvector, pgGraph, LISTEN/NOTIFY
  (live updates), pgmq (durable jobs), pg_cron. Each is used when a step needs it, not before.
- **Extractors** (plugins) read sources into items, relations and claims; **the review lane** holds what a person
  decides; **agents** use the same API over MCP, as users with roles.
- **Views over the same tables, never copies** (S-60): Postgres stays the one truth, and each way of asking is a
  view. Full-text and vectors for recall; pgGraph for traversal (paths, neighbourhoods, what depends on X
  transitively, as the caller, so row-level security holds); a SPARQL endpoint (Ontop, picked in S-59) for
  meaning (classes, subproperties, queries across vocabularies), reasoning at query time; and inference that
  is worth keeping (OWL 2 RL rules) written back as claims, attributed to the reasoner and quoting the rule and
  the claims it fired on, so a retracted premise takes its conclusions with it. Content types carry terms
  (`x-term` on each type and field), and the mappings for both pgGraph and Ontop are generated from them, so
  the views cannot drift apart.

### Slots and the judge: how substrate is pluggable

Substrate is pluggable in two different senses, and the difference is the design.

- **Slots.** Every part on the map sits in a slot named by an interface: the runtime's four verbs
  (`runtime-api`), the secrets verbs (`secrets-api`), Workbench's API and MCP (`workbench-api`,
  `workbench-mcp-api`), the model endpoint (`model-api`), the front door, the graph endpoint. Whatever answers an
  interface can fill its slot: compose or a scheduler, `.env` or a secrets store, Ontop or another SPARQL engine.
  The `options` system lists the known alternatives for each slot, and section 5 is how one is chosen. A slot
  is real only when its interface has a contract test that any filler must pass, and the map says which test
  that is (`morphogen.dev/tests` on the API, `scripts/contract.sh`); Morphogen's structure check reports any
  untested interface, and its judge runs these tests for any change that touches one. Since step 9 every core
  interface has one, and so do the parts beneath them (database, tools, sandbox, repository, evidence log);
  each run is recorded in Workbench as a contract item, pass or fail, against the filler it ran with.
- **The judge is plugged in, not slotted.** Morphogen is reached through `judge-api` like any part, but it is
  not a slot substrate may fill: the loop cannot choose, swap, weaken or tune its own judge (section 7, "who
  decides a change"). Everything else can be replaced by evidence; the judge is replaced only by the owner.

## 5. Catalogs: choosing, not guessing

Most of what substrate decides is a choice between things that already exist: a library, a service, a model, a
vocabulary, a process. It keeps two kinds of catalog so those choices come from evidence rather than from what
a model happens to remember.

- **Catalogs of components**: things it can use, each with what it is for, where it fits, its licence and
  versions, and the evidence gathered about it (tests run, verdicts, problems met). Substrate's own map is one
  (`catalog-info.yaml`, system `core`). The parts removed in step 1 are its first options (system `options`):
  each says where it fits, what interface keeps it possible, and the commit to restore it from.
- **Catalogs of searchable catalogs**: registries it can search when no known component fits. Examples are npm,
  PyPI, crates.io, the Go module proxy, GitHub, apt archives, container registries, the Hugging Face Hub, and
  deps.dev across several of them (system `sources`). Each says how to search it and what metadata it gives.

**A choice is curated, researched and tested.** Search the catalogs. Shortlist candidates as catalog entries
with claims about each (licence, release age, maintenance, fit, quoted from the source). Test the shortlist
against the need, judged by Morphogen where "better" is the question. Pick one and record why. The rejected
candidates stay in the catalog with their evidence. The house rules apply to every candidate: a permissive or
LGPL licence in the default stack, and a release at least two weeks old, pinned exactly.

**How it is done** (S-59): the `research` skill. The need is written first, in `docs/choices/<slug>.yaml`; the
shortlist is tried by a pinned script under `scripts/trials/<slug>/` on the same cases; `substrate:choices`
reads the file into Workbench as a `choice` and its `candidate` items, with licence, releases and activity
quoted from the registries' own answers. When the need alone decides (only one candidate meets it), no verdict
is needed and the choice says so; when two meet it, "which is better" goes to Morphogen.

**Vocabularies are chosen the same way, when they are needed.** Substrate's own small vocabulary (its content
types and the catalog's kinds as classes) is generated, not chosen (step 7). External vocabularies are an option
(section 8): ontology registries become source catalogs (candidates to verify: Linked Open Vocabularies, EBI's
Ontology Lookup Service, BioPortal, schema.org, Wikidata), and a vocabulary is a candidate with a licence,
versions and fit like any library, once data is exchanged with other tools or merged from other systems.

## 6. Where claims come from

| Source | How | Attributed to |
| --- | --- | --- |
| **Observation** | encoders read code, config, running containers, logs and metrics | the encoder's role, quoting what it read |
| **Exploration** | Claude Code reads a system (repository, docs, an API, a registry) and records what it found | the agent, quoting the source |
| **Interviews** | a person answers questions; each statement becomes a claim | the person, quoting the transcript |
| **Verdicts** | `substrate:morphogen` reads Morphogen's evidence log, checking its hash chain first | Morphogen, citing the record in the log |
| **Registries** | `substrate:choices` reads GitHub's and deps.dev's answers about each candidate in a choice | the extractor, quoting the key in the registry's JSON |
| **Inference** | a reasoner applies a vocabulary's rules (OWL 2 RL) to current claims | the reasoner, quoting the rule and the claims it fired on; retracted with its premises |

Interviews matter as much as observation: most of the intended half of any real system lives only in people's
heads. A person's statement is a claim like any other. It can conflict with an observed one, and the conflict
is a gap.

## 7. Acting

Responses are how a gap closes. Each one is declared (name, inputs, what it changes, who may run it), and each
run is recorded as a claim.

- **Builders** change code, config, content types, views or the map: a branch and a pull request on whatever
  forge the repository uses (S-25).
- **Optimizers** tune a parameter (a threshold, a prompt, a skill) and keep it only if Morphogen judges it
  better than what runs now.
- **Other responses**: research a catalog, open a review item, ask a person (an interview), notify the owner.

A response that changes a running system needs a passing verdict or the owner's approval in the review lane.
Reads never do. Approval is never a forge's merge button.

### Who decides a change

Which kind of change it is decides who judges it (S-51). The rule underneath every row: **no one judges a
change to the thing that judges.**

| What changes | Proposed by | Decided by | Why |
| --- | --- | --- | --- |
| A component (code, a skill, a hook, a parameter) to make it better | Claude Code, or one of Morphogen's optimizers (`tune`) | Morphogen's verdict: rules from the base, held-out cases, the red team | the changer cannot reach the evaluator; an optimizer inside Morphogen is still only a candidate source |
| The map (which way a gap closes: revise intent, or fix practice) | Claude Code, from a gap drift found | the owner, in Workbench's review lane | Morphogen reads the catalog as its own rules and refuses any candidate that edits it, so a map revision can never be its own verdict |
| A part added or removed, with no claim to improve anything | Claude Code, in a build step | the step's check, then the map revision above | adding a part is not an experiment; the map records it |
| **The judge itself**: Morphogen's code, its cells and rules (`morphogen.yaml`), its red team, its statistics | anyone, Morphogen's own map skill included | never Morphogen: the ratchet. A red-team test that proves the hole must pass the current judge first; the fix reaches Morphogen's main by a pull request the owner reviews; every earlier cheat must keep failing; A/A checks after a statistics change | a judge that approves changes to itself is the reward hack in its purest form; the recursion stops at a person and a test suite that only grows |
| Who decides, and how much is automated (organization) | anyone | the owner only | section 3: organization is never automated |

When the judge changes, verdicts given under the old one stay what they were. A planned Morphogen addition
re-judges past verdicts under a stricter judge and flags passes that only passed through the hole it closed.
Workbench records each step either way: the proposal, the test that proved the hole, the review, and the
verdicts before and after.

The owner sees Workbench: the review lane (gaps, proposals, verdicts, each with evidence), the map, and search over
everything. Only decisions that are the owner's reach them: organization (section 3), changes to the judge, licences,
money. When the lane gets noisy, fix the noise where it starts (an encoder, a query).

## 8. Options: what substrate stays compatible with

These are good production choices that substrate does not run now. Each is a component in `catalog-info.yaml`,
system `options`, with lifecycle `option`. Each entry says where it fits, the interface that keeps it
possible, when to bring it back, and the commit to restore it from (`a00fb61`, where all of them ran on the
owner's machine on 2026-11-08). The rule: don't build it now, don't close the door on it. One comes back
through section 5, as a choice with evidence, when a step needs it.

| Option | Fits where | Kept possible by | Bring back when |
| --- | --- | --- | --- |
| Model gateway (Bifrost v2.3.2) | between Claude Code and model providers | Claude Code reads `ANTHROPIC_BASE_URL`; nothing assumes direct access | cost must be measured outside the agent, or several providers routed |
| Metrics (Prometheus v3.15.0) | observed half: rates, cost, errors | an observer probe reads PromQL over HTTP (observe.yaml) | a gap needs numbers over time |
| Traces (OpenTelemetry collector 0.163.2) | observed half: who calls whom | `service.name` = the catalog name | a gap needs observed calls, not just code |
| Catalog browser (Backstage, create-app 0.9.3) | a view over the catalog | the catalog stays in Backstage's entity model | people want to browse, or a Backstage plugin is needed |
| Scheduler (Nomad 2.0.7) | runs the services | scripts call only `rt_up`, `rt_down`, `rt_status`, `rt_logs` | many nodes, batch jobs, or an API an actuator drives |
| Secrets store (OpenBao 2.7.1) | holds credentials | scripts read secrets only through `env_value` and `sec_*` | more than one person or machine, or audit needed |
| Bus (pgmq 1.13.1) | work and notices between parts | Workbench already uses pgmq for its jobs (`wb_jobs`) | triggers should start sessions without a person |
| Owner console | one live page for the owner | Workbench's shell is that page now (S-55) | — |
| Front-door plugins (Caddy 2.11.7 with xcaddy) | the one address | Caddy stays the front door (`CADDY_IMAGE`) | a plugin (auth, HTTPS, rate limits) is needed |
| Docker | the container engine | engine-specific code only in `scripts/lib.sh` | a machine without Podman |
| Graph endpoint (Ontop 5.5.0) | SPARQL with reasoning over Workbench's tables, beside PostgREST | a mapping generated from content types' terms; a read-only role | step 7 (picked in S-59, `docs/choices/rdf-endpoint.yaml`) |
| External vocabularies (PROV-O, SPDX, DOAP, SKOS; ontology registries) | terms for content types beyond substrate's own | `x-term` on types and fields, `wb.term`, `wb.mapping` (SSSOM) | data is exchanged with other tools, or merged from another system's terms |
| Remote judge | Morphogen on another machine | `judge-api` (its CLI and MCP tools); the evidence log shipped or served instead of read from this repository's git directory | the changer should not even reach the judge's machine; several substrates share one judge |
| TOSCA, other RDF tools | other tools reading or writing the model | Workbench's SSSOM mappings table; an export is a plugin (Morph-KGC reads the same R2RML) | a tool needs the model in its own terms |
| A forge (Forgejo, Gitea, GitLab) | where pull requests are reviewed | git remotes only (S-25) | a repository lives there |

**Held ideas.** These come from the previous spec. Each can return as a step when a level needs it: working
memory, episodes from sessions, recall reranked by activation, skill utility and promotion, triage at an
automation level, a dispatcher that starts headless sessions. New with S-60: **learning rules**, not only
applying them. A rule miner proposes rules from patterns in the claims (for example, components of this kind
always depend on that); each proposed rule is a hypothesis, judged by Morphogen on held-out claims before any
reasoner may use it. Deduction (step 7) comes first; induction waits until there is enough data to hold out.
After rules, learned models: a catalog of learning methods (AutoML), each a component chosen and judged like
any other, tested on video games and internet research (section 1, direction).

## 9. Build plan

Each step ends with a check anyone can run. [`build.yaml`](build.yaml) holds the same steps with their status.

| # | Step | Done when |
| --- | --- | --- |
| 1 | Cut to the core | the stack is kernel's Postgres, kernel and the tools container; each removed part is an option in the map (section 8); `scripts/check.sh` passes (done) |
| 2 | Autopoietic: one loop on itself | substrate is modelled as its own project at component level with nothing self-only; a gap between the map and what is observed is found, a change closing it is proposed and decided by whoever decides that kind of change (section 7), and Workbench traces gap, change and decision by id (done, S-58) |
| 3 | A content system for the model | the catalog is a content type, read and edited as items, with its claims and drift checks unchanged; a new kind of entry is a new content type with no change to the store (done by Workbench, S-57) |
| 4 | Catalogs to choose from | one real choice is made by searching the source catalogs, shortlisting candidates as entries with cited claims, testing them, and recording the pick and the rejections (done: the graph endpoint, S-59) |
| 5 | Autopoietic, observed: substrate as it actually runs | the observed half covers what runs substrate (the host, containers, settings by name, routes, the APIs and UIs served, plugins, Claude Code's wiring, Morphogen's cells) through extractors that would read any machine the same way; drift compares every kind; a gap step 2 could not see is decided; a route traces to the container that serves it (S-61) |
| 7 | A graph view: traversal, SPARQL, inference | on step 5's data and over the same tables: substrate's own terms on its content types; pgGraph answers a transitive path; Ontop answers SPARQL with reasoning behind Caddy as a read-only role, its mapping generated from the terms; OWL 2 RL inferences land as claims attributed to the reasoner and leave when a premise is retracted |
| 8 | Engineer: the machine and its agents | the owner's machine and its Claude Code setup beyond this repository is a second project, observed by step 5's extractors and with its owner interviewed; the relations between it and substrate are claims; one change closing a gap is judged and applied the same way step 2 changed substrate (needs the owner) |
| 9 | Slots enforced | each core interface on the map has a contract test, the map names it, and an option enters a slot only by passing it; Morphogen's structure check reports no untested core interface |

Step 6, a second unlike domain, was dropped (S-49): the generalist level stays a direction. Steps 7 to 9 were added with S-60 and reordered with S-61: observe first, so the graph view is built on real data; 7 and 8 need 5, 9 needs only 4. External vocabularies became an option.

## 10. Limitations

- **One machine, one owner.** Several owners or sites need federation, which this spec does not cover.
- **Judges are models.** Verdicts are noisy. A/A checks measure that noise but do not remove it, so small
  improvements may not be distinguishable from it.
- **The judge is the one wall.** If Morphogen's separation fails (the changer can see the held-out cases, or
  edit the rules), nothing else stops a reward hack. Its red team and A/A checks run before any loop's results
  are trusted.
- **Interviews cost a person's time.** Step 5 depends on someone willing to answer, and on questions good enough
  to be worth it.
- **Observing a machine is broad.** Step 5 reads what runs substrate; step 8 reads further, only as far as the
  owner names. Settings are read by name, never by value, and anything stored as a source is scanned for secrets.
- **Reasoning is only as good as the vocabulary.** Inferences follow from the terms and rules chosen; a careless
  subclass yields confident wrong claims. They are claims like any other, retractable and attributed, which is
  why the vocabulary is chosen through section 5.
- **The observed half starts thin.** With metrics and traces as options (section 8), what is observed about
  substrate comes from its code and its running containers. That is enough for step 2, but not for every kind
  of gap.
- **Registries differ.** Some have no search API (PyPI), and some limit unauthenticated requests (GitHub).
  Research falls back to the web, and each claim says where it came from.

## 11. Sources

- This repository's `DECISIONS.md` (S-41 onwards for this spec) and `catalog-info.yaml`
- Workbench: `workbench/BRIEF.md`; kernel (https://github.com/OpenReplicant/kernel), its predecessor, retired (S-68)
- Morphogen (https://github.com/OpenReplicant/Morphogen)
- Maturana and Varela, *Autopoiesis and Cognition*, 1980 (organization and structure)
- SSSOM: https://mapping-commons.github.io/sssom/ ; SKOS: https://www.w3.org/TR/skos-reference/
- Backstage's catalog entity model: https://backstage.io/docs/features/software-catalog/descriptor-format
- deps.dev API: https://docs.deps.dev/api/v3/
- Ontop: https://ontop-vkg.org/ ; OWL 2 profiles (QL, RL): https://www.w3.org/TR/owl2-profiles/ ; R2RML:
  https://www.w3.org/TR/r2rml/ ; PROV-O: https://www.w3.org/TR/prov-o/
