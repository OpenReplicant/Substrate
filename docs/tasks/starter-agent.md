# Task: the starter agent, on research tasks first

**Model:** the largest for stage 1 (the trial and the design choices it settles), Opus for stages 2 and 3.
**Needs:** nothing. **First in the order now** (S-98, S-99). Read `docs/contracts/` and the `research` skill.

## What it is

An agent a person gives tasks to, made of components that can each be changed on a verdict, which gets cheaper
and better at the tasks it is actually given. First tasks: **research** (the owner's pick): "which library
does X", "what licence is Y under", "is there something that does Z", answered from registries with sources,
never from memory. It is the `research` skill's job done by a small agent, with Claude Code as the rank it
hands up to and the builder that proposes changes to it.

It is the fallback learner made concrete, on one stream:

| Part | Is | Governed component |
| --- | --- | --- |
| the stream `research` | a question someone asked, as an `input` item (a person in the shell, or an agent through MCP) | no |
| the agent | a model handler that loops: think, call a tool, read the result, until it answers or hands up | its prompt; its step limit |
| its tools | search a registry, fetch a page, recall from the Knowledge Kernel, record a finding. The registries and how to search each come from the map's `sources` system (`substrate.dev/search`), not from code | each tool's description; which registries are offered |
| its notes | what it has learned about doing this work ("GitHub says NOASSERTION: read the LICENSE file"), shown with each task | yes: this is where compile-down lands |
| the hand-up rule | below what confidence, or after which failures, it escalates | yes |
| the route | the agent, a larger free model with the same tools, a Claude Code session with the `research` skill, the person | the order is measured, not set |

## What a finished task is

A **finding**: the question, the answer, and for every fact that decides it a quote and the URL it was read
at, with the date. For "which X", the `research` skill's shape (need, searched, candidates, pick, rejections).

**Outcome**, from two places, neither a model's opinion:

1. **Grounded** (a script): the share of the finding's quotes that are found at their URL in the pages the
   agent fetched. A fact with no quote, or a quote that is not there, counts against it.
2. **What the person did**: accepted, edited, redone or ignored, as a decision in the moderation queue.

**Cost**: the meter's factors (`docs/contracts/cell.md`, rule 3), plus tool calls and wall time.

## How it is judged

The world is the registries behind a **fetch that records**: every search and page the agent reads is kept
(URL, date, body hash, body). A judged run replays from that record, so it needs no network, is the same for
base and candidate, and the scorer can check quotes against exactly what was served
(`docs/contracts/environment.md`: the world, the driver, the scorer; one model held fixed).

- `dev` cases: the seven choices already in `docs/choices/` (their questions, and the registry facts the
  `substrate:choices` extractor confirmed), and questions written for the purpose.
- held-out cases: questions whose answer is a registry field at a recorded date (a package's licence, whether
  a release is two weeks old, which of three candidates has a given feature), written and recorded by the
  operator outside the repository; later, the person's own accepted findings, split by week.

## Stages

1. **Trial and choices** (largest model). Which local model already pulled can drive a tool loop at all (the
   minimum-viable model, S-97): five `dev` questions each, through the gateway, with a scripted set of two
   tools. Record it in `docs/choices/starter-agent-model.yaml`. Settle from what the trial shows: the tool-call
   format the model follows reliably, the step limit, and whether the agent runs in Workbench's server (does
   it have a way out to the registries?) or beside it as a worker that the handlers plugin records.
2. **The agent, usable** (Opus). A source kind in the handlers plugin for inputs that are items someone saved
   (general: nothing in it names research). A plugin for the research stream: the agent handler, its tools,
   the `finding` type, the notes file. `scripts/ask.sh "QUESTION"` and the shell: ask, watch the calls, see the
   finding, accept or edit it. Done when the owner has asked five real questions and decided each.
3. **Judged** (Opus, then the largest for the checks). The recording fetch and replay, the driver and scorer,
   the cases script, the cell for the agent's prompt, then the two judge checks of direction step 3 and one
   compile-down (a lesson from a handed-up task written into the notes) as the first real comparison.

## Tools from elsewhere

An agent's tool can be another project's MCP server or command instead of code written here: it goes on the
map as a reached component, is offered to the agent with a description (a governed component), and its calls
are recorded like any other. That is less work than porting its features, and the judge then says whether
offering it helped. The lead the owner named for codebase chores, `yfedoseev/fossil-mcp` (read 2026-11-15:
Rust, one binary, MIT or Apache-2.0, static analysis with no model, MCP over stdio and a CLI with JSON and
SARIF output, a `check` command with exit codes), fits three ways: a tool for an agent doing codebase tasks;
a `tests` line or a scored metric in a cell (dead code and clones may not rise); and a source of the map at
code zoom (its call graph is components and interfaces). Not adopted here: it goes through the `research`
skill when codebase tasks become a stream.

## Files to touch

Stage 1: `docs/choices/starter-agent-model.yaml`, `scripts/trials/starter-agent/`, `DECISIONS.md`.
Stage 2: `plugins/handlers/` (the new source kind, its test, README), a new plugin directory for the research
stream, `streams.yaml`, `scripts/ask.sh`, `scripts/gateway.py` only if keys need it, the map (rule 8), `CLAUDE.md`'s
command list. Stage 3: as `06-environment-and-baseline.md` lists, with `meter-factors.md` and
`verdict-fields.md` done first.

## Leave alone

`workbench/` core. `repos/morphogen`. `plugins/handlers/ladder.py`'s contract: the tool loop lives inside one
handler, and every model call it makes goes through the gateway with its key. The `research` skill (Claude
Code keeps it; the agent's notes may quote it). No benchmark, no second stream, no ontology work. Queries to
registries carry the question's terms only, never anything about the person or their files.

## Done when

Stage 1: the choice file names the model, with the trial's numbers. Stage 2: five of the owner's questions
answered or handed up, each with a decision, every call visible in the fallback learner's view and counted at
the gateway. Stage 3: a same-against-same verdict that fails, a worse candidate refused, and one compile-down
judged, pass or fail. `scripts/test.sh` and `scripts/check.sh` pass at each stage.

## Changed by S-101 (2026-11-15)

Stage 1 is done (S-100: Granite 4.0 Micro; the OpenAI tools format works through the gateway; the trial's
questions were too easy to be cases). The rest of this brief is carried by three others, which win where they
differ from the text above:

- `environment-package.md`: the agent starts from an environment's file. **No `scripts/ask.sh`**: asking is
  saving an input; there is one way to start.
- `papers-environment.md`: the research stream is reading papers, then reproducing them.
- `codebase-environment.md`: the second stream is chores in a codebase, with other projects' tools interfaced.

What stays from above: the parts table, a finding with a quote and URL for every deciding fact, the two
outcomes, the recording fetch and replay, the route, and "Tools from elsewhere".
