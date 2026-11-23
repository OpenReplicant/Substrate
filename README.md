# Substrate

An agent framework, built around one working system so far: **the assistant**, which you can talk to in text or
out loud with a face. It does real work in the background on models you host, asks before anything leaves your
machine, and improves its own parts under a judge it cannot reach. A **gate** in front of every model call is
learning which calls a compiled skill or a smaller model can answer (being built, `docs/plan.md` step 3).

The idea: you put an **environment** on a system you need. An environment is data in Postgres: the signals that
arrive, the actuators that can be acted on, and a record of everything. With nothing else configured, every
signal goes to an LLM harness (Claude Code), which acts only through gated actuators. That is **pass-through**.
From the record, the system writes **components** that handle what repeats, each with a **card** saying what it
is for, how it is measured and how it is tested. A **judge** tests each new version against the one in use, on
cases its author never saw, and **you** decide what goes live.

It is two products (S-181):

| Part | What it is |
| --- | --- |
| **Substrate** (this repository) | everything that runs: environments, streams and gated actuators, the model gateway and the gate in front of it, the assistant and its voice front end, components with cards, the judge, the UI, and the experiments |
| **[Knowledge Kernel](https://github.com/OpenReplicant/kernel)**, the store | everything known, each statement with who said it, its source and how sure; permissions enforced by Postgres per caller; review before anything counts; recall by words and by meaning (BM25 and pgvector) |

The research behind the gate, impasse-driven compilation after Soar's chunking, is written up in
[MetaSoar](https://github.com/OpenReplicant/MetaSoar); its experiments run here. The judge is an interface (a
candidate in, a verdict out, on cases its author never saw); [Morphogen](https://github.com/OpenReplicant/Morphogen)
is one filler, out of the build for now.

All of that now runs end to end once, on one component (the voice head's replies). The rest of the framework is
described in [`docs/framework.md`](docs/framework.md) and built as the plan's steps need it.

## What runs

Everything is in containers under Podman compose, published on 127.0.0.1 only.

| Part | Where | What it does |
| --- | --- | --- |
| The store | the Knowledge Kernel (`scripts/kernel.sh`), Postgres (`deploy/postgres`) | Wikibase's data model with pinned evidence: things, statements, and the exact span of the source each statement rests on. A changed source flags what cites it, with no model call. Maps of parts, roles and interfaces, and catalogs of candidates with measurements and trade-off notes |
| The environment | `environment/`, schema `env` | Signals logged whole and fanned out as pgmq topics; one queue per actuator behind a gate (`free`, `propose`, `deny`); proposals wait for a person; every action recorded |
| The channel | `environment/channel.py` | Pushes an environment's signals into a live Claude Code session; a signal not acknowledged comes back |
| The gateway | `gateway` (Bifrost), `scripts/gateway.py` | Every model call goes through it under its caller's key and is logged there, not by the caller. Keys decide which providers a caller may reach (voice stays local) |
| The assistant | `environment/worker.py`, service `worker`, the UI's `#/worker` | One agent loop on your own models: the slow model (`slow`, Inkling 2 Mini on the CPU here) with the kernel's memory and a workspace; compiled skills answer without a model. Handing work to the cloud waits for your approval |
| The companion (to retire) | `deploy/companion`, service `companion` | Claude Code on Haiku, on your own Claude login, in its own container with only the channel. It replies, starts background tasks and proposes budget and model changes; it becomes the assistant's `cloud` level (S-181) |
| The companion's environment | `environment/companion.py`, service `environment` | The clock, the gateway's meter of the companion's own spend, the daily budget (background tasks are refused while over it), and the appliers of approved proposals: outside the companion's reach |
| The local models | services `llm` and `llm-fast` (llama.cpp) | Two of your own GGUFs (S-169): a slow capable one on the CPU (`slow`; Inkling 2 Mini here) and a small fast one on the GPU (`fast`; LFM3 1.7B here) |
| The voice head | `voice/`, service `voice`, http://127.0.0.1:8110 | The microphone in over a WebSocket; Silero cuts utterances, Parakeet turns them into text, the fast model decides each turn by the tool it calls (talk, quick tools such as notes, reminders, lookups and search, or hand over), Kokoro speaks each sentence, a face moves with the audio. Talk over it and it stops. Real work goes to the assistant, whose answers are read out (S-170, S-171) |
| Components and the judge | `env.component`, `env.verdict`, `environment/author.py`, `environment/judge.py`, service `judge` | Every version of a component with its card; an author writes new versions from the record; the judge tests them on cases only it can read; you activate |
| The UI | `ui/`, service `ui`, http://127.0.0.1:8100 | The store's pages and maps as diagrams; the companion's page: the conversation, proposals to approve or refuse, the meter, the components and their verdicts |

Who may do what is enforced by Postgres logins, not by convention. The processes that run models can publish
and act, but cannot decide a proposal, change a gate, read the record, or activate a component. The judge can
read everything and record verdicts, but cannot activate anything either. Every signal and action keeps the login
that really wrote it, whatever it claims to be.

## How it improves itself

The loop, as it runs today on the voice head's replies (what the local model is told, and its settings):

1. **The record.** Every utterance heard and every reply said is a signal, with timings, interruptions, handoffs,
   and the component version that produced it.
2. **An author** (the local model, so what you said aloud stays on the machine) reads the active card and the
   *training* slice of the record, and writes a new version: instructions, settings, its own test cases, and its
   reasons. A fixed third of the record, chosen by hash, is never shown to an author.
3. **The judge** (its own container and database login) runs the new version and the active one, case by case,
   on 30 labelled utterances that only its container mounts, on the held-out third of the record, and on the
   card's own tests. It measures whether replies hand work over exactly when they should, whether they are fit to
   be spoken, and how soon the first word comes. Its verdict, with every case's output, is kept whole.
4. **You decide.** Only a version judged better becomes a proposal on the companion page. Approve it, and the
   voice head uses it from its next turn.

Ask for a new version with **Improve voice** on the companion page (the text box, if filled, says why), or tell
the companion to improve how the voice answers.

## Experiments, and what they showed

Each choice was measured before it was made. The scripts are in `scripts/trials/`, the reasons in
`DECISIONS.md`.

**A channel into Claude Code works through the gateway on a Claude login** (S-144, S-145). Bifrost's documented
subscription mode did not forward the login on any version tried (v2.3.2 to v2.5.1, tested with a fake token
against Anthropic's own answer); its `/anthropic_passthrough` route does, with the caller's key still required
and its allowed models enforced. Two Claude Code settings had to change: `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`
turns channels off, and a session with no built-in tools needs `ENABLE_TOOL_SEARCH=false` to see the channel's
tools (without it, the model wrote its tool calls out as text). Then: a message, a reply, a background task,
and a budget proposal you approved, every call in the gateway's log under the companion's key, with no content.

**Hearing and speaking on the CPU** (S-147; `scripts/trials/voice-head`). Three speech-to-text and four
text-to-speech candidates on the same cases: 73 LibriSpeech utterances, and twelve companion-style sentences
spoken by each voice and read back.

| | words wrong | per utterance | memory |
| --- | --- | --- | --- |
| Parakeet TDT 110M, sherpa-onnx | 5.0% | 0.09 s | 610 MB |
| Parakeet TDT 0.6B v3, sherpa-onnx | 4.8% | 0.27 s | 1.4 GB |
| Parakeet TDT 0.6B v3, onnx-asr | 7.8% (one empty transcript) | 0.25 s | 1.4 GB |

| | first audio of a short reply |
| --- | --- |
| Kokoro-FastAPI on the GTX 1070 | 0.10 s |
| Kokoro, kokoro-onnx, CPU | 0.26 s |
| Kokoros (Rust), CPU | 0.41 s |
| Kokoro, sherpa-onnx, CPU | 1.29 s |

Picked: Parakeet 110M and kokoro-onnx, both on the CPU, so the GPU stays the language model's. The 0.16 s is
not worth sharing the card. Every candidate is in the store's catalog with a note on when it would be the better
choice (Kokoro on the GPU if the model moves off this card; Parakeet 0.6B for other languages).

**The local model** (S-149; since replaced by two models, S-169). llama.cpp rather than Ollama, because only llama.cpp keeps a mixture-of-experts
model's experts in system RAM (`--cpu-moe`): Gemma 4 26B-A4B then uses 2.9 GB of the 1070's 8 GB. Gemma 4 thinks
before answering by default, about 6 s before the first word; with thinking off, 0.4 s. The first answer after
the model loads took 14 s while its weights were read in from disk, so the voice head warms it at start. Spoken
turns: about 2 s from the end of your speech to the first word.

**The first loop** (S-151). The author proposed version 2 (lower temperature, shorter replies). The judge's first
verdict said better, on 29 of 30 handoffs against 28 of 30. That is one case, which the rule counts as noise: the
judge had compared rounded rates, and rounding pushed the gap over the margin. Fixed, with a test for that case.
The same card judged again came out the same (29 of 30 for both: the one case really was noise) and was refused.
The first verdict is kept as it was; you refused its proposal.

**Earlier** (S-140, S-142). A diagram library for maps: Cytoscape.js with dagre drew Substrate's own map in
53 ms under the UI's strict content policy. Embeddings for search: on 213 pages no embedding model beat plain
full-text search beyond chance, so none is used until the record gives real queries.

## Running it

Needs git, python3, Podman with compose, and Claude Code on the host; everything else runs in containers.

```sh
scripts/bootstrap.sh       # once: images and the tools container
scripts/up.sh              # the stack and its databases, then scripts/check.sh
scripts/check.sh           # is everything up and wired
scripts/test.sh            # the test suites, each in a throwaway database
```

Settings live in `.env` (made from `.env.example`, mode 600; secrets are generated once). For the local model and
the voice head, set `LLM_MODELS_DIR` and `LLM_MODEL` to your GGUF file and `COMPOSE_PROFILES=llm,voice`.

The companion needs your Claude login, once, in its own container:

```sh
scripts/companion.sh login     # in a terminal: type /login, follow the link, paste the code
scripts/companion.sh attach    # see the session (detach with ctrl-b d)
```

Each time its session starts, Claude Code asks you to confirm the development channel (it is a research
preview); `scripts/companion.sh attach` and press Enter.

Then talk to it in text at http://127.0.0.1:8100/#/companion, or out loud at http://127.0.0.1:8110 (press Start,
allow the microphone; headphones help).

## Privacy

The defaults are in [`docs/privacy.md`](docs/privacy.md): nothing personal leaves the machine unless a rule is
loosened for a named stream, and each loosening is a recorded decision. Loosened so far: your typed messages to
the companion reach Anthropic (S-136). What you say aloud stays on this machine: the voice head, the assistant,
the author and the judge use only your own models, and the assistant hands work to the cloud only when you approve
it. Two quick tools you chose send questions out: Wikipedia lookups and SearXNG search (S-171). The gateway keeps no
message content. The gate's experience keeps your requests word for word, encrypted, deletable and kept only as long as you set (S-182).

## Not built yet

- Components beyond the first; the judge running each case more than once (so smaller differences can be told
  from noise), judging answer quality, and comparing against plain pass-through; holding out whole days.
- The component lifecycle past activation: demotion when you keep overriding one, and the rate of model calls
  per event, the number that should fall as it learns.
- The view (how the environment is laid out for each model) as a tested component; environments nested in one
  another; a review lane in the UI beyond the companion page.
- A VRM avatar for the face, mixed reality on a Quest 3, and the embodied environments after it
  (`docs/plan.md` steps 7 to 10).

## Where to read more

- [`docs/plan.md`](docs/plan.md): the steps, and where each stands
- [`docs/framework.md`](docs/framework.md): the shape of the framework
- [`DECISIONS.md`](DECISIONS.md): every default, every measurement behind it, and why (append-only)
- `CLAUDE.md`: the parts and the rules for working on it

This is the fresh tree (S-137); v1 is tagged `v1-final`, and its plans are in `docs/archive/`.

## Licence

Substrate is under the Apache License 2.0 (`LICENSE`). Some parts it fetches at setup carry their own licences:
espeak-ng (GPL-3.0, inside the speech containers, unmodified, S-146), Parakeet's weights (CC-BY-4.0, NVIDIA),
Kokoro's weights (Apache-2.0), and the model you point `LLM_MODEL` at (its own).
