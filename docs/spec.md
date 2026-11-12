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
| **Engineer** | another system beside itself, from observation, exploration and interviews | able to manage what it models | both systems are in one world model, and one judged change is made to the other (step 8: a system that exists or one that is wanted; first, the machine substrate runs on) |
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
runs now, and kept only on evidence. Section 10 (multi-process, S-74) is the loop that does the distilling:
inputs handled at the cheapest rank that can, and what a dearer rank works out compiled into a cheaper one.

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
(S-19), substrate's Workbench plugin (`plugins/substrate`), and the map's committed export (`catalog-info.yaml`; the map
itself lives in Workbench, `plugins/substrate/MAP.md`). It runs one way for
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
  (system `core`). The parts removed in step 1 are its first options (system `options`):
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

### Labels: where content may go

Privacy is a setting, not a fixed list, because what can be kept local differs by stream and by machine (S-89).
An item or a claim can carry a **label** (to start: public, private, secret). A label is a claim like any other:
who applied it, when and why. The owner's **flow policy** says, for each label, where its content may go: local
models, each cloud provider, Claude Code, the map's export and commits, logs, transcripts, volunteered compute.
Changing it is a decision in the review lane. A stream's default label is part of the policy; a person's streams
default to private, and `docs/assistant/PRIVACY.md` is the default policy for private.

- **Labels travel.** The reasoner records each conclusion's premises and every handler call its inputs, so
  whatever is derived (a conclusion, an answer, a summary, a compile-down, a knowledge-file line) takes the
  strictest label among them. Lowering a label is a decision in the review lane, never a side effect.
- **Enforced where content leaves.** The gateway gives a handler a key cleared only for the providers its
  input's labels allow; Workbench's read roles give Claude Code nothing above its clearance; the export and
  commits carry no labelled item; volunteered compute gets public work only. Each has a contract test (step 28).
- **Air-gapped is a setting.** Every label local-only. The obstacle is the actor: the top rank is a Claude Code
  session, which calls Anthropic's API. So that rank is a slot (step 29), and whether a local agent harness can
  fill it is a judged comparison, re-run as local models are released.

## 8. Options: what substrate stays compatible with

These are good production choices that substrate does not run now. Each is a component on the map,
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
| A private network (WireGuard or similar) | reaching the front door from a phone or another machine | Caddy stays the one address; HTTPS on it | step 30, or a second machine |
| A voice-agent framework (Pipecat, LiveKit Agents) and local speech models | realtime audio and video in, speech out | an environment in the slot (reset, step); models behind the gateway | step 30 |
| Volunteered compute (BOINC-style) | jobs run on other people's machines | the runner slot; results are claims, verdicts stay trusted | step 31, when comparisons outgrow this machine |
| A local agent harness | the top rank without a cloud model | the session rank's contract test | step 29, an air-gapped setting |

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
| 8 | Engineer: a first system beside substrate | a second system, one that exists or one that is wanted, is a domain of its own on the same map, observed as far as its owner allows or mapped before it exists, with its owner interviewed (each statement their claim, quoting them); the relations between it and substrate are claims; one change closing a gap is judged and applied the same way step 2 changed substrate; the test run is the owner's machine (needs the owner) |
| 9 | Slots enforced | each core interface on the map has a contract test, the map names it, and an option enters a slot only by passing it; Morphogen's structure check reports no untested core interface |
| 10 | A business vocabulary, adopted | an organisation's parts (organisation, unit, role, person, resource, process, activity, event, decision, document, measure, goal) are content types whose terms come from published models chosen through section 5 (candidates: W3C ORG, schema.org, REA, a BPMN 2.0 ontology, DMN, OCEL 2.0), with SSSOM mappings; a demo business's map round-trips, and a BPMN 2.0 process imports and exports |
| 11 | The organisation interview | a skill of its own, on the interview's transcript format and extractor, maps a whole organisation (people, roles, resources, processes, handoffs, pain points, time spent) from several people; each statement is that person's claim, and where two people disagree the difference reaches review |
| 12 | Processes as they run | events from the tools a business uses (CSV or tool exports, and OpenTelemetry logs and spans where a tool emits them) land in Workbench as OCEL 2.0 events and objects; a process is discovered from them and checked against the described one; a planted deviation in the demo business's logs reaches review, traced to the statement it contradicts |
| 13 | A baseline, and a judged improvement | measures (cycle time, rework, cost per case) are defined over the events; a process change is judged by Morphogen on time windows it was not tuned on, with an A/A check on the measure, and "no verdict yet" where the data is too thin (a change to how the judge holds out cases: needs the owner) |
| 14 | Deliverables from the map | a current-state report, process diagrams, a prioritised roadmap and staff procedures are generated from the map, each line traceable to its claims |
| 15 | One step automated | an automation engine, picked through section 5 (licence checked), fills a slot with a contract test; one process step in the demo business is automated, its events are observed back, and step 13 judges it |
| 16 | An engagement, packaged | a new client is a new instance (`DB_VOLUME`) with a consultant's role in Workbench, written rules for consent, minimisation and retention of a client's data, and an onboarding path from first interview to first report; tried on one real business (needs the owner) |

Step 6, a second unlike domain, was dropped (S-49): the generalist level stays a direction. Steps 7 to 9 were added with S-60 and reordered with S-61: observe first, so the graph view is built on real data; 7 and 8 need 5, 9 needs only 4.

Steps 10 to 16 (S-73) point the engineer level at a business: a small one, open to changing how it works, with
substrate taking it through the change in place of a consultant or beside one. Nothing new is needed in the
loop. The interview gets what is meant to happen out of people's heads, the events show what does happen, the
difference is drift, the owner of the business decides in the review lane, and the judge says whether a change
improved a measure on time it was not tuned on. What is new is content: terms adopted from published business
models rather than invented, an interview for a whole organisation, and events as the observed half.
OpenTelemetry and OCEL 2.0 sit at different layers: OpenTelemetry carries events from tools that emit it,
OCEL 2.0 says what an event means for a process (which activity, which objects: this order, this invoice). The
demo business comes first, with synthetic events, so the steps have data without a client's privacy at stake. External vocabularies became an option.

Steps 17 to 21 (S-74) build multi-process (section 10). They come before step 10 in the order the build plan
takes them: 17 and 18 give step 12 its streams and events, and the business steps reuse them instead of growing
their own.

| # | Step | Done when |
| --- | --- | --- |
| 17 | Streams, handlers and the record of every call | stream, input, handler and route are content types that any domain can use; every call a handler makes is recorded with its answer or escalation, its cost and, later, its outcome, each a claim; a handler's rank is computed from its measured cost; the hooks and the review lane are on the ladder as its bottom and top; one stream from what already happens (drift's gaps) runs through it |
| 18 | Model calls through one gateway, counted outside the candidate | a model gateway picked through section 5 fills a slot with a contract test; a small and a large model are handlers behind it, each call's cost the gateway's own record of it, never the handler's report; a model call the gateway did not see, or saw under another caller's key, is refused; which models and the monthly budget are the owner's |
| 19 | A first environment, and one judged compile-down | the environment slot (reset and step, as Gymnasium states it) has a contract test; ARC-AGI-1, picked through section 5, is the first environment: one step per task, the predicted grid the action, an exact match the reward, its evaluation tasks held out; three ranks (a script, a small model with a knowledge file, a large model) solve training tasks, every call recorded with its transcript and visible in Workbench's ladder view as it happens; a compile-down from the escalations is judged by Morphogen on evaluation tasks it never saw, by score, cost and escalations per task, with an A/A check; a model handler's model and prompt are searched together, the prompt tuned for each model, and the best pair is judged on held-out tasks against the handler as it is |
| 20 | The idle tier | under a budget, on Workbench's timers and jobs, the idle tier replays escalations into proposed compile-downs, practises on fresh cases, prunes and re-ranks handlers, and proposes streams to subscribe to (each subscription a map change, to review); its spending is recorded and stays inside the budget; it never touches held-out cases (a red-team test) |
| 21 | A person at the top of a stream | a stream whose outcomes are a person's: first this repository's review lane (the owner's decisions), then a personal assistant's streams (which ones are the owner's choice), with privacy rules written and checked before any personal stream is read (settings by name, gitleaks, local models for personal data); questions to the person fall and work accepted unedited rises over held-out weeks |
| 22 | Model calls counted inside Morphogen's judged runs | in a judged run the candidate reaches models only through the gateway the operator names, its calls, tokens and cost per round come from the gateway's record, and a candidate that calls a model around it cannot move a verdict (a red-team test in Morphogen, upstream, first: its PLAN.md phase 7c) |
| 23 | An interactive environment: ARC-AGI-3 | ARC-AGI-3's games, through its toolkit, fill the environment slot and pass its contract test; an episode's steps go up the ladder one action at a time, each frame and action replayed in the ladder view; held-out games stay unplayed until judged; a compile-down from one game's escalations is judged on games it never saw |
| 24 | Recall by meaning, and a catalog of models by task | an embedding model picked from a leaderboard runs here (Ollama, GPU or CPU) behind the gateway; recall is one query over full-text, vectors and graph traversal, each part kept only if it beats the ranking without it on held-out queries from substrate's own history; models are catalogued by task with the scores they were picked on and what substrate measured |
| 25 | Papers as a stream | a query over a paper registry is a stream, as papers are published and in bulk; claims and evidence become stated claims quoting the paper, code becomes catalog candidates, and paper mining is a generator of proposals ranked by what lands; a paper about an agent's architecture becomes an architecture's map for step 26 |
| 26 | Architectures as intended maps, compared on a role | an architecture is a system's intended map with a role claim; first two-way, as Morphogen judges now: the running ladder on ARC-AGI-1 against a Soar-shaped variant (typed escalations, compile-downs from the call trace) at equal metered budgets, each screened by its slots' contracts and a development set first; then the Common Model of Cognition design as a third, under a held-out budget rule (needs the owner); one component of the winner tried in substrate's own core as an ordinary judged change. Needs only the first half of step 19 and step 22 |
| 27 | A paper's method replicated as an architecture | a paper from step 25 is componentized onto an architecture's map (its unfitted parts are gaps naming missing slots), run on the role it claims at the baseline's budget, and recorded as replicated or not beside the authors' claim |
| 28 | Labels, and where labelled content may go | items and claims carry labels (public, private, secret), each a claim; an owner's flow policy says where each label's content may go; labels travel to what is derived from them; the gateway, Workbench's read roles and the export enforce it, each with a contract test; `PRIVACY.md` is the default policy for private |
| 29 | The session rank as a slot; air-gapped as a setting | the top rank (a session with tools) has a contract test and a local agent harness is compared with Claude Code on a role; air-gapped is the flow policy with every label local-only, and the stack comes up from an offline mirror with no call leaving the machine |
| 30 | A realtime assistant with ears, eyes and a face, from a phone | a mobile page over HTTPS on a private network streams audio and frames to an environment here; turns climb the ladder under a time limit, reflexes cheapest; the avatar is drawn on the phone; models run as the flow policy allows; one latency compile-down is judged on held-out conversations (needs the owner) |
| 31 | Compute is a slot; volunteered compute | a volunteer runner fills the runner slot with pinned, sandboxed, deterministic jobs on public work only; results are volunteers' claims, never verdicts; redundancy, canaries and learned reliability; a negative is final only on a quorum or a trusted re-run; planted saboteurs caught |

## 10. Multi-process: inputs handled at the cheapest rank that can

Substrate subscribes to **streams** of inputs: anything it chooses to tune into, not only prompts. A game state,
a new email, a drift gap, a failing check, a hook firing, a timer. Each input goes to the cheapest **handler**
that can handle it well. A handler either answers (a value, its confidence, its cost) or escalates (a reason,
and where to send it, if it knows). The longer write-up is [`multi-process.md`](multi-process.md).

**N ranks, not a fixed ladder.** Handlers are sorted by their measured cost per input (time, money, a person's
attention), so there are as many ranks as there are handlers. The ladder might run from a hook or a script,
through a rule over claims (step 7), a small model with a knowledge file, a large model, a Claude Code session
and several handlers asked at once, to a specialist person and the owner in the review lane at the top.
Consequences:
- Adding a rank is adding a handler, and retiring a rank is retiring one.
- Several handlers can share a rank, each specialised for part of a stream.
- A handler can escalate past the next rank up, or ask several at once.
- Ranks move as costs are re-measured.
- The router, which picks a handler for an input, is a handler too.
- People are ranks.

All of these are components on the map, changed the way section 7 says.

**Every call is a claim.** The input, the handler, its answer or escalation, its cost, and later the
**outcome**: the score, the check passing, the person accepting, editing, redoing or ignoring the work.
Outcomes are the ground truth. Another handler's opinion never is, or the cheap handler would learn the dear
one's mistakes along with its strengths.

**Compiling down is the learning.** What rank *k* works out becomes a change below *k*:
- a line in a knowledge file or a recipe
- a rule the reasoner applies
- a script or hook, once a recipe is fully predictable
- a routing rule

Each is a component change, so Morphogen decides it, on inputs it was not tuned on, against what runs now.
Each kept change cites the escalations it came from, and each rejected one stays a negative result. A handler
whose outcomes fall gets its inputs routed higher until it is fixed or retired. Each form of compile-down is
one entry in the catalog of learning methods (section 1, direction). Lineage: Soar's chunking, ACT-R's
production compilation, Expert Iteration.

**The idle tier** is not a rank. It is how the system spends a budget when no input is waiting. It replays
escalations into compile-downs, practises on fresh cases, prunes and re-ranks handlers, works the map's thin
parts, and chooses which streams to attend to. A new subscription is a map change, so it goes to review. Section
8's held ideas (episodes, skill utility and promotion, a dispatcher of headless sessions) land here.

**What to change next is a stream too.** The space of changes substrate could make to itself has no edge,
so it is never listed; the idle tier spends its budget on proposals instead. Each proposal cites what it comes
from: a gap drift found, an escalation, a failing check, a cost hot spot, a new release in a catalog, or the
owner. The generators of proposals (drift, the escalation miner, a release watcher, a session asked what would
most improve a stream, the owner) are handlers on that stream, and a proposal's outcome is whether it earned a
passing verdict that held afterwards. So generators are ranked by their cost per change that lands, and the
budget goes where proposals pay. Open-ended search (an archive of judged variants kept as stepping stones, as
the Darwin Gödel Machine does) is one generator with a small fixed share, so it can find what the others would
not without starving them.

**Transfer between streams.** What one stream learns can help another in three ways, each judged on the
receiving stream's held-out cases before it stays, so negative transfer is caught like any regression:
- a component compiled down on one stream (a rule, a script, a knowledge file, a prompt) joins another
  stream's ladder as a handler, and is asked on inputs already seen there and scored against their outcomes;
- what Workbench holds (earlier decisions, facts, recipes, each with its claims) is shown to a handler as part
  of its input, so the ladder records what it saw;
- Morphogen's selector starts from earlier verdicts on similar cells.

Two limits hold whatever is judged: a stream's held-out cases never become another stream's knowledge, and
nothing crosses out of a person's domain (step 21's privacy rules).

**Measures and cheats.** For each stream, the measures are inputs by resolving rank, cost per input, outcome,
and escalations per input. Success is resolution moving down while outcomes hold, on held-out cases: seeds for
a game, time windows for a person's streams (as step 13 holds out windows for a business). The red team tries
these first:
- never escalating
- always escalating
- a handler quietly calling a bigger model inside itself
- confidence that doesn't track outcomes
- the idle tier practising on held-out cases
- outcomes taken from a handler's opinion

Model calls are counted outside the candidate. Morphogen's `otel` observer already does that for Claude Code.
Every other model is reached through the gateway (step 18), and a handler's cost per call is the gateway's record
of it, so a model call the gateway did not see is refused. Inside Morphogen's judged runs the same rule is step
22.

**Environments: streams that act.** Some streams are a loop over time, not one input and one answer: a game,
a person's calendar, later a body. Each turn, an observation comes in, a decision goes up the ladder, an
action goes out, and the next observation shows what it did. Robotics and reinforcement learning already
have one interface for that loop, an environment that is reset and stepped (`reset() -> observation`,
`step(action) -> observation, reward, terminated, truncated, info`, as Gymnasium (MIT) states it), and
ARC-AGI-3's toolkit already follows it. An **environment** is a slot with that interface and a contract
test. An **episode** is an input whose calls are its steps, and its outcome is its reward. Actions pass a
gate the stream declares: a game's are free; a person's world gets proposals the person accepts, edits or
ignores, until a compile-down earns more on held-out weeks. Several streams can feed one decision (the
calendar and the inbox for one reply; the frame and what the last moves did, for one game move). They meet
in the input a handler is shown, never inside a handler where the ladder cannot see them.

**Watching it work.** Every call can be seen as it happens, in Workbench's ladder view: which rank was asked,
what it answered, how sure it was, why it escalated, and what it cost. For an episode, each step and the frame
it acted on are shown in order. A stream may keep each call's transcript (its prompt, the reply and the
reasoning a model returns) in Workbench; a game's stream does, and a person's does only when its privacy rules
say so (step 21). The gateway never keeps content.

**What lands on its own.** A compile-down lands on a passing verdict. A new subscription, a new rank and
anything that reads a person's stream go to the review lane. Privacy rules come before any personal stream is
read (step 21).

**Architectures are intended maps.** An agent architecture (the ladder that runs now, the Common Model of
Cognition design at `a00fb61`, a Soar- or ACT-R-shaped variant, the method a paper describes) is written as
the intended half of a system with no observed half yet: its parts, the slots they fill, and how they connect.
Every part is a gap until something builds it, the same way a system the owner wants starts (section 3). An
architecture's map carries one claim that matters: on this **role** (a stream and its outcome measure), this
arrangement does better than the baseline at equal cost. That claim is a hypothesis like any other.
- **A role** is a stream with its outcome and its held-out cases: ARC-AGI first (step 19), then whatever the
  owner names. The best architecture for a role is a rank, measured, never declared, and it moves when a model,
  a paper or the baseline changes.
- **Most of an architecture is shared.** Variants differ from the baseline in a few components (how recall
  ranks, how an escalation is typed, how a handler is ranked, what a compile-down is built from), so a
  comparison is mostly component against component, in slots that already have contract tests.
- **A paper's method is componentized onto a map** (steps 25 and 27). Its parts that fit a slot become candidates;
  parts that fit none are gaps on its map, and those gaps name the slots substrate lacks. The paper's reported
  numbers are the authors' claims. Substrate's own run on the role's held-out cases is the evidence, so the
  store keeps a record of which published claims replicated here and which did not.
- **Runs are separate systems.** Each architecture is built and run as its own system beside substrate, never
  inside it. A component crosses into substrate's own core only as an ordinary change, judged against what runs
  now (section 7), so nothing an architecture learns can reach the judge.
- **Equal budgets.** Every architecture in a comparison gets the same model budget, enforced by the gateway's
  meter (step 22), so "better" cannot mean "spent more".
- **Cheap screens first.** A candidate must pass its slots' contract tests, then a small development set, before
  it costs a judged run. Screens and runs are paid from the idle tier's budget (step 20), and the generators
  that propose architectures are ranked by cost per architecture that wins.
- **Two first, then many.** Morphogen judges one candidate against one base, so the first comparison is the
  running ladder against one variant (step 26). A third architecture waits for the held-out budget rule below.
- **Held-out cases wear out.** Many comparisons against the same held-out cases fit to them slowly even when no
  single run cheats. Each role keeps a held-out budget: fresh cases where a stream can make them (game seeds,
  new weeks), and a reusable-holdout rule where it cannot. How the judge holds out cases is the owner's call
  (section 7).

**Compute is a slot; volunteers are sources.** What runs a job (a screen, a replication, a variant's run) is a
slot with a contract test, and volunteered compute is one filler for it (step 31). A volunteer's result is a
claim attributed to them, never a verdict, and each volunteer has a reliability learned from results later
confirmed or contradicted. Only public work goes out (labels, section 7). Final verdicts stay on trusted compute,
and whoever proposed a candidate never runs it. Jobs are deterministic (a pinned image, a fixed seed, local
weights checked by hash) so results compare exactly, each goes to several volunteers who do not know of each
other, and canary jobs with known answers are mixed in. Sabotage is lopsided: a faked win is caught by the
trusted re-run before anything lands, but a faked loss quietly kills a good idea. So a negative is never final
from one run, and a refuted candidate keeps the sources of its negatives, to reopen if one proves unreliable.

**A realtime assistant.** A conversation is an environment whose turns climb the ladder under a time limit
(step 30). Reflexes (speech starting and stopping, barge-in, a backchannel) are the cheapest rank, a small local
model answers fast, and a larger one is asked when it must be. A phone reaches it through a page served over
HTTPS on a private network, since a browser allows its microphone and camera only on a secure page; the avatar
is drawn on the phone from the speech it says. Which models may hear and see is the flow policy's (section 7).

## 11. Limitations

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

- **Cheap ranks are only as good as their outcomes.** A stream with a slow or vague outcome (a person who
  rarely says whether a draft was right) teaches slowly, and compile-downs on it wait for enough held-out data
  to judge.
- **Comparing architectures costs compute.** A full judged run of one architecture on one role is many model
  calls, and a fair comparison needs several runs of each. Without outside funding, roles stay few, screens stay
  strict, and local models carry most runs.
- **Labels are a policy, not a guarantee.** They stop substrate's own flows. A cloud model shown public data
  may still infer private facts, what a person pastes into a session is outside them, and unlabelled data is
  only as safe as its stream's default.
- **Volunteers can be wrong on purpose.** Redundancy, canaries and learned reliability bound sabotage; they do
  not remove it, which is why verdicts stay on trusted compute.

## 12. Sources

- This repository's `DECISIONS.md` (S-41 onwards for this spec) and `catalog-info.yaml`
- Workbench: `workbench/BRIEF.md`; kernel (https://github.com/OpenReplicant/kernel), its predecessor, retired (S-68)
- Morphogen (https://github.com/OpenReplicant/Morphogen)
- Maturana and Varela, *Autopoiesis and Cognition*, 1980 (organization and structure)
- SSSOM: https://mapping-commons.github.io/sssom/ ; SKOS: https://www.w3.org/TR/skos-reference/
- Backstage's catalog entity model: https://backstage.io/docs/features/software-catalog/descriptor-format
- deps.dev API: https://docs.deps.dev/api/v3/
- Ontop: https://ontop-vkg.org/ ; OWL 2 profiles (QL, RL): https://www.w3.org/TR/owl2-profiles/ ; R2RML:
  https://www.w3.org/TR/r2rml/ ; PROV-O: https://www.w3.org/TR/prov-o/
