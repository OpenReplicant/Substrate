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
in kernel, its own catalog, the same encoders, drift checks and judge. Nothing in the loop works only on itself.
That is what makes it self-modifying, and what makes several systems in one world model ordinary: each is a
project, and the relations between them (this one manages that one; this component calls that API) are claims
like any other.

The same loop, pointed at widening targets, gives three levels:

| Level | It models | Which makes it | Proven when |
| --- | --- | --- | --- |
| **Autopoietic** | itself: its components (services, skills, hooks, parameters) and its map | self-modifying | a gap in its own model is found, a change closing it is judged, and the verdict lands as claims (step 2) |
| **Engineer** | another system beside itself, from observation, exploration and interviews | able to manage what it models | both systems are in one world model, and one judged change is made to the other (step 5) |
| **Generalist** | anything that can be described as components, by growing what a domain needs: content types, vocabularies, encoders, code, views | adaptable | a direction, not a build step: where kernel's content model points |

Each level depends on the one before. Self first, because the system is right here and every claim can be
checked. Engineer is the same loop aimed at a second system, with the first still in view. Generalist is
where the foundation leads: a new domain may bring code and a view of its own, but it should not need a new
store, a new judge or a different loop. Managing systems of components is the scope; going further is left
open (S-49).

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
practice that turned out better. Which way is a decision, made in kernel's review lane with the evidence beside
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
| **Kernel** | the store and the model: a content system on Postgres with claims as its assertion type | `repos/kernel` |
| **Claude Code** | the actor: explores, interviews, researches, builds, maps; its skills are substrate's procedures | you |
| **Morphogen** | the judge: a change lands only with a verdict the changer cannot reach | `repos/morphogen` |

The glue is this repository: scripts that bring the parts up and connect them, the tools container they run in
(S-19), and the map (`catalog-info.yaml`). It runs one way for now: compose with Podman, secrets in `.env`.

### Kernel as a content system

Kernel is a claim log with ontologies, shaped as a content management system on Postgres (kernel D-101,
`docs/content.md`, PR OpenReplicant/kernel#112):

- **Content types** are pack classes with SHACL shapes; **items** are entities; **versions** are artifacts. A
  content type can come with its own view.
- **Claims** are the assertion type and the index over everything else: attributed, quoting their evidence,
  belief-scored, scoped, bitemporal, written only by change sets. Claims are what substrate reasons over and
  what verifiers check. Everything else (documents, transcripts, code, packages) is what claims cite.
- **Ontologies and aliases are content and taxonomy.** A vocabulary is a pack; relations between vocabularies
  are mapping claims (SKOS `exactMatch` and `closeMatch`, SSSOM-shaped when a mapping set needs its own
  metadata). A domain keeps its own terms, and mappings relate them, rather than translating everything into
  one schema (S-33).
- **System graphs use the catalog's entity model.** Components, systems, resources, APIs, groups and their
  relations, kept in Backstage's own names (kernel D-100) because that is the most widely used way owners
  declare systems. No Backstage server is needed (S-38). A catalog can hold any kind of thing: a service, a
  package, a customer, a process.
- **Postgres does the rest.** Row-level security (clearance), full-text search and pgvector (recall), pgGraph
  (neighbourhoods and paths), LISTEN/NOTIFY, pg_cron and pgmq are already in kernel's image. Each is used when a
  step needs it, not before.

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
LGPL licence in the default stack (kernel D-11), and a release at least two weeks old, pinned exactly.

## 6. Where claims come from

| Source | How | Attributed to |
| --- | --- | --- |
| **Observation** | encoders read code, config, running containers, logs and metrics | the encoder's role, quoting what it read |
| **Exploration** | Claude Code reads a system (repository, docs, an API, a registry) and records what it found | the agent, quoting the source |
| **Interviews** | a person answers questions; each statement becomes a claim | the person, quoting the transcript |
| **Verdicts** | `encoder-morphogen` reads Morphogen's evidence log (kernel D-99) | Morphogen, with PROV lineage to the record |

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

The owner sees kernel's UI: the review lane (gaps, proposals, verdicts, each with evidence) and recall over
everything. Only decisions that are the owner's reach them: organization (section 3), kernel changes, licences,
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
| Metrics (Prometheus v3.15.0) | observed half: rates, cost, errors | kernel's `observer-prometheus` reads PromQL | a gap needs numbers over time |
| Traces (OpenTelemetry collector 0.163.2) | observed half: who calls whom | `service.name` = the catalog name | a gap needs observed calls, not just code |
| Catalog browser (Backstage, create-app 0.9.3) | a view over the catalog | the catalog stays in Backstage's entity model | people want to browse, or a Backstage plugin is needed |
| Scheduler (Nomad 2.0.7) | runs the services | scripts call only `rt_up`, `rt_down`, `rt_status`, `rt_logs` | many nodes, batch jobs, or an API an actuator drives |
| Secrets store (OpenBao 2.7.1) | holds credentials | scripts read secrets only through `env_value` and `sec_*` | more than one person or machine, or audit needed |
| Bus (pgmq 1.13.1) | work and notices between parts | pgmq is already an extension in kernel's image | triggers should start sessions without a person |
| Owner console | one live page for the owner | kernel serves its own UI and MCP | kernel's UI is not enough to act from |
| Front-door plugins (Caddy 2.11.7 with xcaddy) | the one address | kernel's Caddy stays the front door | a plugin (auth, HTTPS, rate limits) is needed |
| Docker | the container engine | engine-specific code only in `scripts/lib.sh` | a machine without Podman |
| TOSCA, RDF tools | other tools reading or writing the model | kernel's mappings pack; export as N-Quads (kernel D-45) | a tool needs the model in its own terms |
| A forge (Forgejo, Gitea, GitLab) | where pull requests are reviewed | git remotes only (S-25) | a repository lives there |

**Held ideas.** These come from the previous spec. Each can return as a step when a level needs it: working
memory, episodes from sessions, recall reranked by activation, skill utility and promotion, triage at an
automation level, a dispatcher that starts headless sessions.

## 9. Build plan

Each step ends with a check anyone can run. [`build.yaml`](build.yaml) holds the same steps with their status.

| # | Step | Done when |
| --- | --- | --- |
| 1 | Cut to the core | the stack is kernel's Postgres, kernel and the tools container; each removed part is an option in the map (section 8); `scripts/check.sh` passes |
| 2 | Autopoietic: one loop on itself | substrate is modelled as its own project at component level (services, skills, hooks, parameters) with nothing self-only; a gap between the map and what is observed is found, a change closing it is proposed and judged, and recall traces gap → change → verdict by claim ids |
| 3 | Kernel as a content system | the catalog is a content type in kernel, read and edited as items, with its claims and drift checks unchanged (needs the owner: a kernel change) |
| 4 | Catalogs to choose from | one real choice (a component a step needs) is made by searching the source catalogs, shortlisting candidates as entries with cited claims, testing them, and recording the pick and the rejections |
| 5 | Engineer: another system beside itself | a real system the owner picks is a second project in the same world model, its graph cited from at least one interview and one observed source; the relations between it and substrate are claims; and one change to it is judged and applied the same way step 2 changed substrate (needs the owner: which system) |

A sixth step, a second unlike domain, was dropped (S-49): the generalist level stays a direction.

## 10. Limitations

- **One machine, one owner.** Several owners or sites need federation, which this spec does not cover.
- **Judges are models.** Verdicts are noisy. A/A checks measure that noise but do not remove it, so small
  improvements may not be distinguishable from it.
- **The judge is the one wall.** If Morphogen's separation fails (the changer can see the held-out cases, or
  edit the rules), nothing else stops a reward hack. Its red team and A/A checks run before any loop's results
  are trusted.
- **Kernel changes are the owner's call.** Step 3 is a kernel PR; substrate prepares it and waits.
- **Interviews cost a person's time.** Step 5 depends on someone willing to answer, and on questions good enough
  to be worth it.
- **The observed half starts thin.** With metrics and traces as options (section 8), what is observed about
  substrate comes from its code and its running containers. That is enough for step 2, but not for every kind
  of gap.
- **Registries differ.** Some have no search API (PyPI), and some limit unauthenticated requests (GitHub).
  Research falls back to the web, and each claim says where it came from.

## 11. Sources

- This repository's `DECISIONS.md` (S-41 onwards for this spec) and `catalog-info.yaml`
- kernel (https://github.com/OpenReplicant/kernel): `docs/decisions.md`, `docs/content.md` (PR #112)
- Morphogen (https://github.com/OpenReplicant/Morphogen)
- Maturana and Varela, *Autopoiesis and Cognition*, 1980 (organization and structure)
- SSSOM: https://mapping-commons.github.io/sssom/ ; SKOS: https://www.w3.org/TR/skos-reference/
- Backstage's catalog entity model: https://backstage.io/docs/features/software-catalog/descriptor-format
- deps.dev API: https://docs.deps.dev/api/v3/
