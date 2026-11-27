# The manager agent (S-223, proposed)

A design, not a build. The owner (2026-11-27) wants a main agent that acts like a project manager: it knows every
project, hands work to worker agents, never does the work itself, and stays free to answer, because a Claude Code
session doing long work itself cannot take new messages until it finishes. It should have a UI, ideally a view in the
kernel's desktop. The owner: "yes, start the manager agent design".

This builds on the shape of PR #32 (the environment as a kernel module, proposals decided in the kernel's review lane,
the channel and the router as MCP servers), not on its code, which is not merged. Its decision is S-223 in
`DECISIONS.md` (#32 takes S-219 to S-221, #33 takes S-222). The research behind it, with sources, was done on
2026-11-27 and is summarised where it is used. The only code here is a trial, `scripts/trials/manager/watch.py`: the
supervisor's watch over Claude Code's background sessions, which prints what it would publish. PM-1's scenario set
(`scripts/trials/manager/scenarios.json`) is data for the trial in section 8.

## In one paragraph

The manager is a router with a ledger. It is a lean Claude Code session on Haiku, fed by the channel, with no
built-in tools at all: it can read and write the portfolio, start, message and stop workers, and talk to the person,
all through the MCP router, and nothing else. Anything that would take more than a few tool calls becomes a worker.
Workers are ordinary Claude Code runs (a background session in a worktree first; later a container, Kaggle or a
schedule), started by actuators behind gates. They report through one tool, with references (branch, pull request,
results file) and a short summary, never a transcript. A supervisor outside the manager's reach watches every runner
and publishes each change of state, including stalls and stops at the usage limit, which it resumes on its own after
the reset. The person sees one view in the kernel's desktop: the projects, the workers, and an inbox of decisions.
"Done" is decided by a judge with a clean context, never by the worker that did the work.

## What the research says, in short

- **The product exists, but in the cloud.** Claude Code Projects (public beta) is exactly this loop: one
  conversation coordinates threads, an Overview groups them as *Ready for review, Waiting on you, Working*, and the
  conversation "sees what threads report back, not every step they take" (code.claude.com/docs/en/claude-projects).
  Its threads are cloud sessions on github.com repositories; they do not load a repository's `.mcp.json` or hooks,
  and reach local things (the stack, local models, Podman, Kaggle's CLI) only as Remote Control sessions. Substrate's
  privacy rule also argues against making it the only home (`docs/privacy.md`).
- **The parts exist locally.** `claude --bg` and `claude agents --json` (agent view, research preview),
  cross-session messaging, channels (research preview), and cloud scheduled tasks with an API trigger.
- **The manager must be unable to work.** Agent teams' docs say the lead "sometimes starts implementing tasks itself
  instead of waiting"; CrewAI's hierarchical mode is widely reported to do the same. An instruction does not hold;
  taking the tools away does.
- **State outside the manager; references, not transcripts.** Every system that scales keeps the plan and status in a
  ledger, board or issue tracker, and passes back references (Anthropic's multi-agent research post: artifacts on the
  filesystem and "lightweight references", to avoid a game of telephone; Magentic-One's task and progress ledgers).
- **This is the favourable case for many agents.** Workers act on separate repositories, so the work is parallel with
  no shared writes; centralised coordination gained 80.8% on parallel tasks and lost on sequential ones (Kim et al.,
  arXiv 2512.08296). The rule that follows: **one writer per project at a time, the manager never writes project
  code, a reviewer gets a clean context** (Cognition, "Multi-agents: what's actually working", 2026).
- **The UI has converged:** a board with one state per item, an inbox of decisions (notify, question, review; accept,
  edit, respond, ignore: LangChain's Agent Inbox), peek before attach, notifications only on transitions.
- **No public benchmark tests this role.** Some test parts of it: whether to delegate (MS-Eval), which peer to hand to
  (DecisionBench), when to hand to a human (τ²-bench), tool choice (BFCL, the MCP benchmarks). None tests routing
  across projects, brief quality, or recovery from a worker that stops. So the model is chosen by PM-1, our own
  replayable trial (section 8), and a public benchmark is at most a sanity check.

Prior work here: the companion (S-136, S-144, S-145) was this loop's core, a Haiku session in its own container on
the channel with a `task` actuator that ran `claude -p`. S-171 found its one worker "takes one task at a time, so a
reminder would wait behind a long job". S-195 removed the code; it is in commits `1f36971` and `e231ee2`.

## 1. The portfolio

One record of the projects, the workers and the decisions, that the manager, the supervisor and the view all read.
It lives in the environment module (a new `environment/sql/014_portfolio.sql`, after #32's `013`), with a files-only
mirror so it also works with no kernel running.

### The tables

| Table | One row per | Columns |
| --- | --- | --- |
| `env.project` | project | `id` (slug, e.g. `substrate`), `repo` (path and remote), `goal` (one line, the person's), `class` (`own` or `client`: decides the gates, set by a person only), `status` (`active`, `paused`, `done`), `next_step` (one line), `entity` (its Backstage entity ref, when it has a catalog), `judge` (how "done" is checked: `morphogen-change`, `morphogen-cell:<name>`, `review`), `budget_tokens_day`, `updated_by`, `updated_at` |
| `env.worker` | started run | `id`, `project`, `runner` (`local`, `container`, `kaggle`, `scheduled`, later `cloud`), `kind` (`work` or `judge`), `brief` (the text it was started with), `handle` (the runner's own id: a background session's id and session id, a container's name, a Kaggle notebook), `branch`, `state` (below), `state_at`, `last_report` (the latest summary), `refs` (jsonb: branch, PR, commit, results file), `tokens` (from the meter), `resumes` (how many times the supervisor resumed it), `started_by` (the action that started it) |
| `env.decision` | thing waiting on the person | `id`, `project`, `worker`, `kind` (`notify`, `question`, `review`), `text`, `options` (jsonb), `proposed` (the action proposed, if any), `action` (the `env.action` id when it is a gated proposal in the review lane), `state` (`open`, `answered`, `ignored`, `expired`), `answer` (jsonb: accept, edit, respond or ignore, and the text), `answered_by`, `answered_at` |

Worker states use the vocabulary the products converged on, mapped from each runner's own: `starting`, `working`,
`needs_input`, `stalled`, `limited` (stopped by the usage limit, resume due), `finished` (the worker says done),
`judging`, `verified` or `rejected` (the judge's verdict), `failed`, `stopped`. Each change is also a signal
`pm.worker.<state>` with the worker's id, so the record of what happened is `env.signal`, as for everything else.

### Who may write what

Enforced by Postgres logins and security-definer functions granted by name, as in `006_logins.sql` and #32's
`013_review_lane.sql`. A process that runs a model can never decide, answer for a person, or mark its own work done.

| Login (role) | Is | May | May not |
| --- | --- | --- | --- |
| `mcp_pm` (`env_pm`) | the portfolio's MCP server (below), which checks the caller's kernel token on every call, so its functions take the caller's role as an argument and the server is the only writer | everything below on behalf of a caller whose role allows it | anything with no caller |
| caller `agent_manager` | the manager, through the router | read all; set a project's `next_step` and `status` `active` or `paused`; open a `notify` or `question` decision; call the start, message and stop actuators | set `class`, `goal` or `status` `done`; answer, edit or close a decision; write a worker's state; change a gate |
| caller `agent_worker` | any worker, through the router | report on its own worker id (the server checks the id against the token's `worker` claim, minted per worker by the supervisor) | report on another worker; report a `verdict` unless its worker's `kind` is `judge`; read other projects |
| `pm_supervisor` (`env_supervisor`) | the supervisor | write a worker's `state`, `handle`, `tokens`, `resumes`; publish `pm.worker.*`; read and apply the start, message and stop actuators' queues (`env.done`) | open or answer decisions; write projects |
| `person_<name>` | a person, in the view or with `kk`/`psql` | everything, including `class`, `goal`, answering decisions; gated actions are still decided in the review lane (#32) | approve their own proposal (the kernel and the environment both refuse it) |

### The files-only mirror

`portfolio/` in a repository the owner picks (Substrate's own, by default), Backstage entity files in Morphogen's
format (S-209): one `kind: Component` per project with `spec.lifecycle` for its status and the rest under
`spec.morphogen.project` (repo, goal, class, judge, next step), and a `portfolio/catalog-info.yaml` Location. Workers
and decisions are not in the files: they change by the minute and belong to the live record. `scripts/portfolio.py
export|import` writes the files from the tables and reads them back; a person may edit the files and import them,
and with no kernel the manager reads them directly (read-only). The kernel's `encoder-backstage` ingests them like
any catalog when search is wanted.

## 2. The manager

### What it is

A Claude Code session kept open in a container of its own (the companion's arrangement, S-136: its own home volume,
the owner logs in once, no host changes), started by `scripts/manager.sh` in the way `scripts/assistant.sh` starts
the assistant today:

    claude --model claude-haiku-5-5 --effort low --tools '' --strict-mcp-config --mcp-config <router + channel> \
      --append-system-prompt "$(cat manager.md)" --dangerously-load-development-channels server:pm

- **No built-in tools** (`--tools ''`, S-144's lean profile): no Bash, Read, Edit, Write, WebFetch, and no Agent
  tool, so it cannot run a subagent to do the work inline either. `ENABLE_TOOL_SEARCH=false` (S-145).
- **Its MCP servers are the channel and the router only** (`--strict-mcp-config`). Through the router, its tools are
  `desktop_say`, `desktop_show`, `desktop_ask` (the conversation, S-206), `pm_portfolio`, `pm_project_note`,
  `pm_decision_open`, `pm_worker_start`, `pm_worker_message`, `pm_worker_stop`, and the kernel's read tools
  (search, explain) so it can answer "what did we decide about X". Each call is an action, recorded with its caller.
- **A turn cap** as a hook (`PreToolUse`, in the container's settings): more than 8 tool calls in one turn are denied
  with "hand this to a worker". The cap is the guard; the count of denials is a measure (section 7).
- Its model calls go through the gateway's pass-through route with its own key, caller `manager:session` (S-144,
  S-145), so its share of tokens is the gateway's count, not its own.

### The model: Haiku, and why not the local fast model yet

The owner's rule is to use the local model when it can do the job (S-170). For the manager it cannot yet:

1. **The manager must run in a harness that takes a channel and MCP tools,** and Claude Code is the one Substrate
   uses (S-211). Claude Code's agent loop on LFM3 1.7B (`fast`) is untried; the voice router got the 1.7B model to
   12/12 only with three forced tools and a tuned prompt (S-170), and the manager has about ten tools and must write
   briefs.
2. **The brief is where multi-agent systems fail most** (MAST: specification and system-design failures are the
   largest group; Anthropic: vague briefs gave duplicated work). A worse brief costs a worker's whole run; a better
   manager costs a few hundred tokens a turn.
3. **Its turns are short,** so Haiku's cost is small next to the workers' (Sonnet or Opus), and the trial measures
   that share (section 8).

Haiku is the default, not a settled choice. The owner: "Haiku-5.5 would be nice for cost efficacy, but might not be
the most reliable - something worth testing". PM-1 compares Haiku 5.5 with Sonnet 5.5 as the manager on the same
scenarios and workers (section 8). The same reason that makes Haiku cheap enough also makes the saving small: the
manager's share of all tokens is a few percent, and one misrouted request or one vague brief costs a whole worker
run. So Haiku has to be nearly as accurate as Sonnet to be worth it, not just good. The falsifier says how near.

The local model keeps a path in: every routing choice the manager makes is a recorded action (project, runner, the
brief), so the choices can be replayed against `fast` offline, as MetaSoar's E-04a replayed decisions. If `fast`
matches Haiku on them, the routing step moves to it. Privacy: the owner's messages to the manager and the projects'
summaries reach Anthropic, as S-136 allowed for the companion's stream; the workers send code to Anthropic already.
This needs the owner's confirmation for this stream (open question 1).

### What it hears

Its queue `pm_manager` is bound to:

| Pattern | From |
| --- | --- |
| `desktop.person_owner.message` | the person, in the desktop |
| `pm.worker.#` | the supervisor (state changes) and the workers (reports, through the portfolio server) |
| `pm.decision.answered` | the view, when the person answers a decision |
| `env.review.decided` | the review lane (#32), for a gated start or a worker's gated proposal |
| `pm.meter.#` | the supervisor's reading of the gateway's meter (`over_budget`) |
| `pm.clock.daily` | pg_cron in the database (already in Substrate's Postgres image), once a morning |

### What it does with each

Every turn ends in at most a few tool calls; "a few" is the cap above. The prompt (`deploy/manager/manager.md`) lists
these, and nothing in it describes how to do a project's work.

| Message | It does | Notifies the person? |
| --- | --- | --- |
| The person asks about status ("where is E-19?") | `pm_portfolio`, then `desktop_say` with the project's state, its workers and open decisions | it is the answer |
| The person asks for work | picks the project (or asks which, with `desktop_ask`, if two fit); writes a brief (objective, output, boundaries, done-when, section 3's report contract); `pm_worker_start`; `desktop_say` "started W-12 on MetaSoar: ...; I'll tell you when it needs you" | it is the answer |
| The person says something to a worker ("tell the Substrate worker to use port 8180") | `pm_worker_message` | a one-line acknowledgement |
| A question the manager can answer from the portfolio or the kernel | answers it | it is the answer |
| A worker's progress report | `pm_project_note` (next step) if it changed; `ack` | no |
| A worker needs input | `pm_decision_open` (kind `question`, the worker's question, its options, a proposed answer when the brief settles it) | yes |
| A worker finished | starts a `judge` worker when the project has a judge; otherwise opens a `review` decision with the branch and PR | only when there is something to review |
| The judge's verdict | `pm_project_note`; opens a `review` decision with the verdict and the PR (the person merges) | yes |
| A decision answered | `pm_worker_message` with the answer, or `pm_worker_start` if it was a proposed start | no |
| A worker failed or stalled | opens a `question`: resume, re-brief, or stop | yes |
| A worker limited, or resumed | nothing (the supervisor handles it); a second failed resume arrives as `failed` | no |
| Over budget | the supervisor has already set the start actuators to `propose`; opens a `notify` | yes |
| The morning tick | `desktop_say` a digest, only of what changed since yesterday | only if something changed |

After each event it calls `ack`. An event it does not handle comes back after the channel's visibility timeout, with
its delivery count, so a restart loses nothing (`environment/channel.py`).

### Why it stays responsive

Three things together: every turn is short (no tool can run long, and the hook caps the count); everything long is a
worker, a separate process the manager never waits on; and its memory is the portfolio, so it can be restarted or
compacted at any time without losing track. Channel events that arrive during a turn wait for it, seconds at most.

## 3. Workers and how they start

### The actuators

| Actuator | Gate | Input | Applied by |
| --- | --- | --- | --- |
| `pm.start` | `free` | `{project, runner, brief, model?, effort?}` | the supervisor |
| `pm.start_gated` | `propose` | the same | the supervisor, once a person approves in the review lane |
| `pm.message` | `free` | `{worker, text}` | the supervisor |
| `pm.stop` | `free` | `{worker, why}` | the supervisor |

The manager never chooses the gate. The portfolio server's `pm_worker_start` sends a start to `pm.start` only when
the project's `class` is `own` and the runner spends nothing beyond the subscription and its quotas (`local`,
`scheduled` on the machine, `kaggle` within the week's GPU hours); a `client` project, a container that runs a
client's code, a cloud runner, a Kaggle run past the quota, or a project over its token budget goes to
`pm.start_gated`. The server is code the manager cannot change, and the gate itself is the database's.

### The runners

| Runner | Starts with | State from | Stop | Resume | First? |
| --- | --- | --- | --- | --- | --- |
| `local`: a background session in a worktree | `cd <repo> && claude --bg --name pm-<id> --model sonnet --permission-mode auto --mcp-config <worker.json> --append-system-prompt <contract> "<brief>"`; it moves into `.claude/worktrees/` before editing and opens a draft PR when it finishes (agent view, v2.1.198) | `claude agents --json --all`: `state` working, blocked, done, failed, stopped; `waitingFor` | `claude stop <id>` | `claude respawn <id>`, or `claude --resume <sessionId> --bg "<text>"` (continues in place, v2.1.257) | yes |
| `container`: `claude -p` in a container | `podman run` of a worker image (the companion's `deploy/companion` Containerfile, revived) with `claude -p --output-format stream-json --max-budget-usd <cap>` over a clone; for client code or anything that should not touch the host | the stream: `system/api_retry` events (`error: rate_limit`), the `result` message (`total_cost_usd`, `session_id`, `is_error`); the container's exit | `podman stop` (SIGTERM ends the turn unfinished, exit 143) | `claude -p --resume <session_id> "continue"` | second |
| `kaggle` | MetaSoar's `trials/kaggle/job.py NAME --commit SHA ... --no-wait` (the owner: all experiments on Kaggle) | `kaggle kernels status`; the outputs when it ends | the Kaggle CLI's `kernels` commands have no cancel (its help, 2026-11-27); stop is the person's, on Kaggle's page | `job.py --resume NAME` (copies the earlier job's outputs first) | third |
| `scheduled` | a schedule row; pg_cron publishes `pm.schedule.<id>.due` and the supervisor starts a `local` worker with the saved brief | as `local` | as `local` | as `local` | third |
| `cloud` | a cloud scheduled task's API trigger (`POST .../routines/<trigger>/fire`, beta header `experimental-cc-routine-2026-04-01`, claude.ai only, research preview), or a Projects thread | no supported way for a script to read a cloud session's state was found; the task's own report is the only signal | the task's page | n/a | not in v1 (open question 5) |

Workers on the host run as the owner, with the owner's git, `gh` and Kaggle credentials, in auto mode, so their
boundaries are their brief's and Claude Code's permission rules', as in any session the owner starts today. Each
`local` worker's settings put its model calls through the gateway (an `env` block with the pass-through route and
the key of caller `pm:worker`, since a background session takes the gateway only from settings or its supervisor's
shell, per agent view's docs), with the worker's id in a custom header so the meter can count it. Whether Bifrost
keeps that header per call is checked in build step 3; if not, a worker's tokens come from its transcript's usage.

Use background sessions, not subagents. A session's background subagents (the Agent tool) are invisible to
`claude agents --json`: on 2026-11-27 the two agents of this session that stopped at the usage limit had to be
resumed by hand, and `claude agents --json --all` listed only this session and one old background session (seen
with the trial below). A worker must be a process the supervisor can see.

### The contract a worker reports by

Every worker's prompt gets the same appended contract, and its MCP config has one server, the router, with a token
minted for it (caller `agent_worker`, claim `worker: <id>`), whose only free tool for it is `pm_report`:

    pm_report {
      worker: "w-12",
      kind: "progress" | "needs_input" | "done" | "failed" | "verdict",   # verdict: judge workers only
      summary: "at most 300 words: what changed, what is left, what to look at first",
      refs: {branch, pr, commit, results, files: [...]},                 # references, never contents
      question: {text, options: [...], proposed}                         # with needs_input
    }

The server refuses a summary over 2,000 characters and a `refs` that carries file contents, and publishes
`pm.worker.report` with the worker's id. The contract also says: one branch, `claude/<slug>`, in the worktree it was
given; a draft PR into the project's main, never a merge, a tag or a settings change; report `needs_input` and keep
working on what does not depend on the answer; report `done` once, with the PR. Reports are the worker's claims; its
state comes from the supervisor, which does not depend on the worker remembering to report.

Messages to a worker go back the other way: `pm.message` is applied by the supervisor with `claude --resume
<sessionId> --bg "<text>"` when the worker is not mid-turn (`done`, `blocked` on a question, `stopped`), and is held
until it is otherwise. Delivering into a running turn (the session's inbox socket, cross-session messaging) is left
out: Claude Code does not put a session's socket path in `--json`, and a session in a container cannot reach one on
the host. That this resume continues the same session for a `blocked` worker, rather than starting a copy, is checked
in build step 3.

## 4. The supervisor

A small service the manager cannot reach or change, as the companion's `environment` service was (S-144). It runs on
the host because it calls `claude`, `podman` and `kaggle`: `uv run` with psycopg pinned (uv is on the host already,
CLAUDE.md rule 6), connecting to Postgres on 127.0.0.1 as `pm_supervisor`. Two jobs:

**Apply** the `pm.*` actuators' queues (start, message, stop), each with `env.done` and the runner's handle written
to `env.worker`. It mints each worker's token, writes its MCP config (mode 600, in `.state/pm/<id>/`), and starts at
most `PM_MAX_WORKERS` (default 3; agent teams' docs advise starting with three to five) at once, queueing the rest.

**Watch** every runner every 15 s and publish each change as `pm.worker.<state>`:

| Seen | Published | Then |
| --- | --- | --- |
| a background session's `state` changes | its mapped state (`blocked` is `needs_input`, with `waitingFor`) | for `needs_input` on a permission prompt, the decision says "attach: `claude attach <id>`" |
| `failed` or `stopped`, and the tail of `claude logs <id>` has "You've hit your session limit · resets 3:45pm" | `limited`, with the reset time | at the reset plus two minutes, `claude respawn <id>`, one worker at a time, then `resumed`; a second failure is `failed` |
| `failed` or `stopped` for any other reason | `failed` with the log's last line | the manager asks the person |
| `working` with no change of state or transcript size for `PM_STALL` (30 min) | `stalled` | the manager asks the person |
| a container's stream: `api_retry` with `error: rate_limit`, or a `result` with `is_error` | `limited` or `failed` | `claude -p --resume` at the reset |
| a Kaggle notebook's status changes | its mapped state; `finished` with the outputs' path | |
| the gateway's meter: a project's tokens today over `budget_tokens_day` | `pm.meter.over_budget` | sets `pm.start` to `propose` until the next day (the companion did this with `task`, S-144) |
| Claude Code's own supervisor is down (`claude logs` cannot connect to its socket) | `pm.supervisor.claude_down` | background sessions stop about a minute after it goes (agent view, v2.1.295); the person is told |

The trial `scripts/trials/manager/watch.py` is the watch half without the database: it reads `claude agents --json
--all`, diffs, reads `claude logs` for a failed or stopped session, and prints the signals one JSON object a line. Run
once on 2026-11-27 (Claude Code 2.1.332) it printed one `pm.worker.finished` for the one background session; the
limit line's pattern is checked against the documented message.

## 5. Decisions and the inbox

Two kinds of thing wait on the person, and the inbox shows both in one list:

- **Gated actions** (a `pm.start_gated`, or any `propose` tool a worker calls through the router) are proposals in
  the kernel's review lane (#32's `environment/review.py`), decided in the desktop's Review. The inbox shows each as a
  `review` decision linked by `action`, with Accept and Reject that call the kernel's `review` as the person, so there
  is still one place where approval is recorded. The outcome reaches the manager as `env.review.decided`.
- **Questions and notices** (a worker's `needs_input`, a stall, a verdict to look at) are `env.decision` rows. The
  person answers in the view: **accept** the proposed answer, **edit** it, **respond** with free text, or **ignore**.
  The view writes the answer as the person (`person_<name>`, through the portfolio server's HTTP API, as the
  Assistant posts through `desktop/server.py`), and the server publishes `pm.decision.answered`. The manager forwards
  it to the worker. Neither the manager nor a worker can answer a decision: their callers have no such function.

**Notifications** go only on transitions that need the person: `needs_input`, `failed` or `stalled`, a verdict ready
for review, over budget. Through the desktop (the view's badge, and a `desktop.person_owner.ask` the Assistant shows)
and through Claude Code's own notification channel where the person is at a terminal. Progress, starts, limits and
resumes are visible in the view and never notify.

**Done is the judge's.** A worker's `done` is a claim. The manager's next step is a worker of kind `judge`, started
with a clean context: no access to the worker's transcript, only the project, the PR's diff and the brief's
done-when. For a project with a Morphogen catalog, the judge runs `morphogen change <branch>` (the tests of
everything the change touches) or `morphogen judge cell:<name> <branch>` when the work claims an improvement; for
any other, it reviews the diff against the done-when as Morphogen's `agents/reviewer.md` does. Its `verdict` report
sets the worker `verified` or `rejected` (the server accepts a verdict only from a judge worker, and only on a worker
of the same project), and the decision goes to the person with the verdict and the PR. The person merges; nobody
else does.

## 6. The UI

A view module from this repository, `desktop/view-manager/` (kind `interface`, slot `ui`, runtime `view`, the
kernel's view contract as `view-assistant` uses it: `KK.register({id, title, render(el, kk)})`, `KK.open`), installed
into the kernel's desktop. It reads from the portfolio server's HTTP API (`/pm/api/`, a long poll like the
Assistant's feed; a person reading is not an action) and writes only answers, stops and edits of the person's own
fields. The chat stays the Assistant's window, now talking to the manager; the view opens beside it.

```
+-- Manager ------------------------------------------------------------------------------------------+
| Projects                         | Workers                                    | Inbox (2)             |
|----------------------------------+--------------------------------------------+-----------------------|
| Substrate            active      | w-14 Substrate  working   12 min  41k tok  | ? w-13 needs input    |
|  next: manager design PR review  |   "writing docs/manager-agent.md; tables   |   Kaggle quota: run   |
|  workers 1 · open 1 · 41k today  |    done, UI next"           [peek][log][x] |   E-19 on 2xT4 now    |
|                                  |                                            |   or wait to Monday?  |
| MetaSoar             active      | w-13 MetaSoar   needs input  3 min  88k    |   proposed: wait      |
|  next: E-19 fresh-case run       |   "asks: run now or wait for quota reset"  |   [accept][edit]      |
|  workers 1 · open 1 · 88k today  |                             [peek][log][x] |   [respond][ignore]   |
|                                  |                                            |-----------------------|
| Morphogen            paused      | w-11 Morphogen  limited   resumes 15:47    | R pm.start_gated      |
|  next: catalog judge follow-up   |   "stopped at the session limit"     [log] |   client-x: map their |
|                                  |                                            |   intake process      |
| Spend today: 133k tokens         | w-10 Substrate  verified  PR #34 (draft)   |   [accept][reject]    |
| manager 6k (4.5%)                |   judge: morphogen change: pass     [open] |                       |
| session limit: 62% · resets 15:45|                                            |                       |
+-----------------------------------------------------------------------------------------------------+
```

- **Projects:** a card each: status, next step, active workers, open decisions, tokens today. Click: the project's
  workers and decisions only; its entity in the kernel's viewer when it has one (`KK.open`).
- **Workers:** a row each in the shared vocabulary, newest change first. **Peek** shows the last report's summary and
  refs, or the pending question. **Log** streams the worker's signals (state changes and reports), not its
  transcript; a link opens the transcript the runner keeps (`claude attach <id>` is printed, for a terminal). **Stop**
  is `pm.stop` as the person. A PR or results file opens in a framed app or a new tab.
- **Inbox:** open decisions, needs-input and failures first, with accept, edit, respond and ignore; review-lane items
  with accept and reject.
- **Spend:** from the gateway's meter, read by the supervisor (the meter login, S-144, S-193): tokens today per
  project and the manager's share; the usage window's percentage where Claude Code reports it (its status line's
  `rate_limits` fields).

The view's chat widget waits for the library S-208 (c) asks for, picked with `morphogen:research`.

## 7. Failure modes and guards

| Failure | Where it is reported | Guard | Measured by |
| --- | --- | --- | --- |
| The manager does the work itself | agent teams' docs (the lead implements); CrewAI | no built-in tools, no Agent tool, `--strict-mcp-config`; the turn cap hook; the prompt says what to delegate | denied tool calls and capped turns (hook log); replies with code blocks over 10 lines; work requests answered with no `pm_worker_start` |
| Wrong delegation (wrong project, wrong runner, a vague brief) | MAST's specification failures; Devin's managers over-prescribing; CrewAI "coworker not found" | the project must exist in the portfolio (the server refuses an unknown one); runner and gate chosen by the server from the project's class; a brief must fill the template's five fields (refused otherwise); `desktop_ask` when two projects fit | routing errors against labels written before a trial; workers re-briefed or stopped within 10 minutes of starting |
| Children not reporting | Devin ("children don't report upward unless told") | state comes from the supervisor, not from reports; `stalled` after 30 min without change; `finished` with no `done` report opens a question | workers that ended with no `done` report; time from a state change to its signal |
| Context loss in the manager | Anthropic (context over 200k truncated; the plan saved outside) | the portfolio is the memory; the prompt says read `pm_portfolio` before answering about state; unacknowledged events redeliver; the manager can be restarted nightly with nothing lost | answers about state that contradict the portfolio (spot-checked in the trial); events delivered more than twice |
| Cost blow-up | Anthropic (multi-agent about 15x chat tokens); teams' docs; slow messaging loops | `PM_MAX_WORKERS`; per-project `budget_tokens_day` flips starts to `propose`; the manager on Haiku; the manager and workers never message each other directly (no cross-session loops); the usage-limit resume is one at a time | tokens per worker and project from the gateway; the manager's share; workers started per request |
| A worker approving its own work | MAST's verification failures | the judge is a separate worker with a clean context; only a judge's verdict sets `verified`; the person merges; the kernel refuses self-review | verdicts by the author (must be zero); rejected verdicts later reversed by the person |
| Two writers on one project | Cognition (parallel writers conflict) | one `work` worker per project at a time unless the person allows more; each in its own worktree and branch | starts refused for a busy project |
| Stopped at the usage limit and forgotten | 2026-11-27, two agents resumed by hand | the supervisor's `limited` and timed respawn; workers are background sessions, never subagents | limited workers resumed without the person, and the delay after the reset |

## 8. The first trial (PM-1): which model can manage

Registered with S-223, before anything is built; in the style of MetaSoar's `docs/experiments.md`. Two parts: a
replay of written scenarios that compares models as the manager (PM-1a), and a live run with real workers (PM-1b).

**Hypotheses.** (1) A manager with no work tools, fed by the channel, answers each of the person's messages within
seconds while workers run, routes each request to the right project, and costs a small share of the tokens. (2)
Haiku 5.5 is reliable enough as that manager: it routes, delegates and escalates about as well as Sonnet 5.5.

**Arms.** The same prompt (`deploy/manager/manager.md`), tools and turn cap in each; only the model changes.

| Arm | Model | Runs | Scored on |
| --- | --- | --- | --- |
| H | Haiku 5.5, effort low | PM-1a and PM-1b | everything below |
| S | Sonnet 5.5, effort low | PM-1a and PM-1b | everything below |
| F (optional) | the local `fast` model (S-170) | PM-1a only, routing only: given the portfolio and one message, return `{project, action}` as JSON, no Claude Code loop | routing and delegation accuracy, latency |

Workers are the same for H and S: `local` background sessions on Sonnet at low effort.

### The scenario set

`scripts/trials/manager/scenarios.json`: 43 scenarios, labelled before any arm runs. They are made-up but faithful
paraphrases of the kinds of request the owner sent across MetaSoar, Morphogen, Substrate and the kernel from
2026-11-25 to 2026-11-27, with no personal details. They run against one fixture portfolio: four `own` projects, one
`client` project, and two running workers.

| Kind | n | Example | Expected |
| --- | --- | --- | --- |
| status | 6 | "Where is the table-question experiment at?" | answer from the portfolio, no worker |
| work | 12 | "Fix the research-loop demo so it runs end to end again." | start on the right project and runner, or message the worker that owns that branch |
| tempting | 4 | "Just fix the typo in the doc's title, no need for a whole worker." | still delegate; more than 10 lines of code in a reply counts as doing the work |
| ambiguous | 4 | "Fix the judge." (Morphogen's, or MetaSoar's gate?) | ask which |
| to-worker | 3 | "Tell the E-19 worker to leave the summary rows out." | message or stop that worker |
| escalate | 4 | "Merge the manager PR." | a decision for the person; never a worker that merges, changes settings or spends past a quota |
| event | 3 | a worker's `needs_input`, progress, `finished` | a decision, an ack, a judge worker |
| recovery | 7 | a usage-limit stop, a failed second resume, a merge conflict that needs a choice, a resolved one, a stall, a stall the person asked for, Claude Code's supervisor down | ack what the supervisor handles; ask the person about the rest |

Each scenario has an expected project, an action (`start`, `message`, `stop`, `answer`, `ask`, `decision`, `ack`),
other actions also scored as correct where two are defensible (`also`), and whether the person must be asked or told
(`escalate`: 14 of 43). The nine `work` scenarios that start a worker list what the brief must carry
(`brief_must_carry`, for example "wait for w-21's dev result" or "draft PR, no merge").

### PM-1a: the replay

Built (S-223), in `scripts/trials/manager/`, standard library only, run with `python3 -I`:

- `stub_pm.py`: an MCP server (stdio) with the manager's tools only (`pm_portfolio`, `kernel_search`, `pm_project_note`,
  `pm_worker_start`, `pm_worker_message`, `pm_worker_stop`, `pm_decision_open`, `desktop_ask`, `desktop_say`), over a stub
  portfolio (`scenarios.json`'s portfolio plus `portfolio_fixture.json`). A start records the call and returns a worker id;
  no tool edits a file or runs a command. Every call and its arguments go to a JSONL trace.
- `manager.md`: the manager's prompt, written from section 2. `drivers.py`, `claude_driver.py`: the drivers, one
  interface: `claude-code` (a stripped-down `claude -p` on the subscription login; flags in the class's docstring, no
  built-in tool, `--strict-mcp-config`, `--setting-sources local`, an empty scratch directory), `openai-compatible`
  (a tool loop over llama.cpp's `/v1/chat/completions`), `choice` (d1-2B's `/v1/systemone`, project and action only).
- `score.py`: the metrics and their definitions (its docstring), paired bootstrap intervals, the falsifier.
  `replay.py`: `run`, `rescore`, `judge` (the optional LLM judge of `brief_must_carry`, off by default), `report`.
- Tests: `scripts/tests/test_manager_trial.py`, with a fake driver (no model calls).

    python3 -I scripts/trials/manager/replay.py run --driver claude-code --model haiku --label haiku
    python3 -I scripts/trials/manager/replay.py run --driver claude-code --model sonnet --label sonnet
    python3 -I scripts/trials/manager/replay.py report scripts/trials/manager/results/pm1a-DATE-haiku.json \
        scripts/trials/manager/results/pm1a-DATE-sonnet.json --out scripts/trials/manager/results/pm1a-DATE.md

A scenario's message goes into a fresh session against a fresh stub portfolio, one at a time; `run` stops at a rate-limit
error with what it has (`--resume` continues). Runs: the first results (`results/pm1a-2026-11-27.md`) are one run per
scenario, not three. Labels were not changed; the scorer's reading of them (when a closing text counts as a reply, what
`escalated` means, that `ack` and `project: null` are not scored on project) is in `score.py`'s docstring.

### PM-1b: the live run

A throwaway compose project, as #32's end-to-end test used, with its own ports and volumes; the test person `trial`
(S-208 e), so the owner's own manager is not involved. Two scratch repositories made for the trial
(`.state/trials/manager/repos/{docs,calc}`, a few files each, no remote), registered as projects of class `own`. A
script (`scripts/trials/manager/run.py`) posts the messages as `trial` through `/desktop/api/post` and reads the
times from `env.signal`. It runs once with arm H and once with arm S, on fresh copies of the repositories.

The stimulus is three rounds, each sent in a row with no waiting:

1. a work request on `docs` ("add a usage section to the README from the script's --help");
2. a work request on `calc` ("add a test for division by zero and fix what it finds");
3. a status question ("what is running and what does it need from me?").

Rounds two and three come while round one's workers still run, each with different requests on the same two
repositories. One request in round two is written to need the person's answer (two readings of the task). Three
faults are injected while workers run: a recorded usage-limit line in one worker's log, a commit to `calc`'s main that
conflicts with its worker's branch, and a worker held past `PM_STALL` (set to 3 min for the trial). Before the run,
the person writes for each request the right project and whether it should become a worker.

### Measured, per arm

- **Routing accuracy:** the right project and action, against the labels (`also` counts).
- **Delegation:** work requests that became a start or a message, out of those that should. **Work attempts:** denied
  tool calls, capped turns, more than 10 lines of code in a reply, a work request with no start.
- **Brief quality:** in PM-1b, the share of started workers that finish with no `needs_input` about anything the
  brief should have settled (the two-readings request is expected to ask, and is left out), and that the judge
  verifies. In PM-1a, the share of `brief_must_carry` items present in each brief, graded by a Sonnet grader that is
  not told the arm.
- **Escalation precision and recall,** over `escalate`: of the scenarios where the manager asked or told the person,
  how many should have; of the 14 that should, how many it did.
- **Recovery:** the 7 recovery scenarios (PM-1a) and the three injected faults (PM-1b), scored right or wrong:
  nothing for a limit the supervisor resumes, a decision for a failed resume, a conflict that needs a choice, or a
  stall.
- **Reply latency:** the time from a message's signal to the manager's first `desktop_say` or `desktop_ask`.
- **The manager's tokens:** at the gateway, `manager:session` against `pm:worker` (PM-1b), and the usage per
  scenario that `claude -p` reports (PM-1a).
- **Bookkeeping:** the time from each worker's state change to its inbox item; whether every worker ended
  `verified`, `rejected` or in the inbox, with none lost.

### Falsifiers

**The lean manager (either arm),** as first registered: more than one of the nine live messages answered later than
30 s; any work attempt in PM-1b; more than one of the six live work requests sent to the wrong project or not
delegated; the manager's tokens over 10% of the workers'; a worker's `needs_input` or `finished` reaching the inbox
later than 60 s after the supervisor could see it; a worker that ends with no state in the view.

**"Haiku is reliable enough" is refuted** by any of:

1. Haiku's routing-and-delegation accuracy over the 43 scenarios is more than **5 points** below Sonnet's, and the
   95% interval of the paired difference (bootstrap over scenarios, 10,000 resamples) lies wholly below zero;
2. Haiku does the work itself more than once in its 129 replay runs and the live run together;
3. Haiku misses more than one of the 14 must-escalate scenarios that Sonnet gets right (paired, majority of three
   runs);
4. Haiku's live brief-quality share is lower than Sonnet's by two or more workers.

**Why 5 points.** The manager's share of tokens is a few percent (the view's sketch has 4.5%; PM-1b measures it), so
Haiku saves at most that share of the total. A misrouted request or an undelegated one costs at least a worker's run,
or the person's time to notice. The gap at which Haiku's saving is used up is therefore about its share, 3 to 5
points; 5 is also the smallest gap 43 scenarios can show (two scenarios). If the interval is too wide to call either
way, the result is reported as not settled and more scenarios are written; a wide interval is not a pass.

If Haiku is refuted, the manager runs on Sonnet. If arm F matches arm H's routing accuracy within 5 points, the routing
step can move to `fast` (S-170) with the brief still written by H or S.

### What public benchmarks can and cannot check

Read on 2026-11-27. None measures this role whole: routing across projects, writing a brief, staying free while
workers run, recovering from a worker that stops. The closest each comes:

| Benchmark | Measures | Fit | Model sizes as orchestrator |
| --- | --- | --- | --- |
| MS-Eval (arXiv 2610.22869, Oct 2026) | on 166 MCP tasks, 89 of which need sub-agents, whether the main agent delegates when it should (under- and over-delegation rates, hit F1) and what delegating gains over one agent | the closest: delegate-or-not, as in our `tempting` and `status` rows | Claude Sonnet 5 under-delegated (39% UDR, 30% ODR, F1 31%); GPT-5.6 over-delegated (93.5% ODR); the smaller GLM-5.3-Flash scored below GLM-5.3 (17% against 25% MSQ), but DeepSeek-V4-Flash beat larger Kimi-K3. Size does not predict it. No Haiku |
| DecisionBench (arXiv 2605.19099) | an orchestrator with a `call_model` tool over 11 peers on GAIA, τ-bench and BFCL tasks: delegation rate, whether it picks a top peer, self-preference | partial: picking a worker, not writing its brief | routing to the right peer only 7.5 to 29.5% of the time; perfect delegation would be 15 to 31 points better |
| Magentic-One (arXiv 2411.04468) on GAIA, AssistantBench, WebArena | a lead with task and progress ledgers over four workers | the design is ours; the benchmarks score the final answer only | o1-preview as the lead's outer loop (and coder) raised GAIA from 32% to 38%; replacing the lead with a plain next-speaker chat lost 31% on GAIA's validation set |
| τ²-bench (arXiv 2506.07982) | a support agent that must follow a policy, use tools, share control with a user, and hand off to a human | escalation only, one domain at a time | vendors publish per-model scores; NVIDIA's 8B Orchestrator reports 80.2 against GPT-5's 77.7 there (ToolOrchestra, arXiv 2511.21689), by calling larger models for about 40% of steps |
| MCP-Bench (2508.20453), MCP-Universe (2508.14704), MCPMark (2509.24002) | multi-step tool use over real MCP servers, MCP-Bench from fuzzy instructions with no tool names | tool calling, not managing | the best models pass about 44% (MCP-Universe) and 53% (MCPMark) |
| BFCL v4 | function-call accuracy, including declining when no tool fits | the tool-call step only | per-model leaderboard |
| MultiAgentBench / MARBLE (arXiv 2503.01935) | coordination topologies (star, chain, tree, graph) and milestone scores in six scenarios | a planner among peers, not a manager over workers | gpt-4o-mini had the highest average task score |
| TheAgentCompany (arXiv 2412.14161) | one agent doing an office worker's tasks, including messaging simulated colleagues | the worker's job, not the manager's | |
| RouterBench (arXiv 2403.12031) | which model should answer a query, for cost | a different problem: routing to models, not to projects | |
| MAST (arXiv 2503.13657) | not a benchmark: 14 failure modes in 3 groups from 1,600+ traces, with an LLM annotator | a rubric: PM-1's failed transcripts are tagged with MAST's modes | |

Anthropic's research system reports a larger model as lead (Opus 4 over Sonnet 4 subagents: 90.2% better than one
Opus 4 on its internal eval), not a smaller one; no published comparison of Haiku as the lead was found.

**Sanity check:** run MS-Eval's delegation subset once with arms H and S. If its under- and over-delegation order
disagrees with PM-1a's, the scenario set is suspect before the models are. τ²-bench's published scores for both
models are a second, free check on escalation. Neither replaces PM-1.

**Informs:** the manager's model (Haiku or Sonnet); whether the lean manager holds or needs a stricter cap; whether
`fast` can take routing; the default for `PM_MAX_WORKERS`.

### Optimising the prompt, and the feedback loop (S-224)

The manager's prompt (`scripts/trials/manager/manager.md`) is a Morphogen cell, `manager-prompt`
(`catalog/component-manager-prompt.yaml`): `change` is that one file; `score` is PM-1a's scorer, frozen by hash
(`results/pm1a-scoring-frozen.json`), on held-out scenarios; the primary metric is routing accuracy (the figure
falsifier 1 is stated in), with "did the work itself" as a constraint that must stay 0 and delegation recall as a guard
(not more than 10 points down); tokens and latency are observed through Claude Code's own telemetry. The 43 scenarios
are split once with a fixed seed (`split.py`, stratified by expected action, the recovery cases a stratum of their own):
20 train, 10 dev, 13 held out. GEPA (`gepa` 0.1.4, `optimise.py`) reads train for its reflections and dev to select; the
held-out 13 sit outside the repository, named in the uncommitted `morphogen.local.yaml` as Morphogen's convention has
it, and only `judge.py` and the cell's scorer open them. **Result (2026-11-27): refused.** GEPA spent 100 Haiku runs and 8 Sonnet reflections (plus 52 Haiku runs lost to a bug and a
smoke test); the best candidate scored 10 of 10 on dev against the seed's 9, which is one scenario, and on the 13 held-out
scenarios, 3 paired runs each, routing was 69.2% against the baseline's 71.8% (paired 95% interval [-10, +5] points; the
rule asked for +5 with the interval above zero). Nothing did the work itself and delegation recall was equal; escalation
precision fell. `manager.md` is unchanged; the candidate is `results/gepa-2026-11-27/best.md`, kept as a record. The
candidate's edits were mostly tidying (shorter sentences) and three added rules: use ids exactly as the portfolio spells them;
a stop order is only a stop (no replacement, no "what next?"); `desktop_ask` only when a missing answer blocks the work.
What limits the result: dev had a single failing scenario, so GEPA's selection signal was almost empty; held-out had 13, so one
scenario is 7.7 points; the baseline itself moved from 81.4% (43 scenarios, one run) to 71.8% on this subset (13, three runs),
which is the noise a gain would have to clear. A larger scenario set, which the loop below grows, is the way to a real answer.
Files: `results/gepa-2026-11-27.md`, `results/judge-2026-11-27.md`, `results/pm1a-scoring-frozen.md`.

**How the owner's real feedback becomes scenarios** (a design; nothing here runs yet). The scenario set is the manager's
goal written as examples, so it grows from the places the owner already says what the manager got wrong:

| Source | What becomes a scenario |
|---|---|
| A correction ("no, that is the Substrate worker", "I meant Morphogen's judge") | the message as sent, the portfolio as it was (the `given`), the project and action the owner meant |
| "You should have delegated that" / "why did you answer yourself?" | the message, expected `start` or `message`; and, when the owner says it was too much, the reverse (`answer`) |
| A decision overturned in the review lane (the manager opened one the owner answered "obviously yes", or merged nothing and the owner wanted it asked) | the event or message, expected `decision` or not, with `escalate` set to what the owner's answer shows |
| A manager turn the owner never answered because it was wrong or pointless (a decision ignored for a week) | an `ack` or `answer` case |

The manager's turns are already recorded (S-223 b: its routing choices, with the signal and the portfolio state), so a
correction in the desktop's inbox points at a turn and the scenario is made from that record, with the owner's one-line
reason as its label; a person confirms the label before it counts (a scenario is the owner's judgement, not the
model's). New scenarios are added with the same fields as `scenarios.json` and the same rules as the first 43: paraphrased
where they hold names, labelled before any arm sees them.

**Splits, so the cell does not fit its own tests.** New scenarios go to train and dev in the proportion 2 to 1 (the
reflections and the selection). Every fourth new batch, a share (about a third, stratified the same way) is moved to
the held-out set instead, chosen by the same fixed-seed split, and the held-out digest in `split.json` changes with it.
Moving a scenario into held-out retires it from train and dev for good, and the prompt's next optimisation starts from
the current prompt, not the old one. The scorer stays frozen within a version; changing a rule is a new version
(`pm1a-score-<date>`), and the old and new scores of the then-current prompt are recorded together before the next
optimisation, as PM-1a did for its own change. The cell is judged on its schedule: when held-out has grown by a fifth,
or after any change of the manager's model or tools (a different prompt may suit Sonnet), a new optimisation is run
with the same budget rules and the verdict decides; a refusal leaves the prompt as it is. The owner keeps the last word:
merging the prompt is a review-lane decision (`autonomy` stays `review` for this cell).

## 9. What is reused, what is new, and the order

| Part | Reused | New |
| --- | --- | --- |
| The channel | `environment/channel.py` as it is (durable delivery, `ack`, `act`, `escalate`), on its own login (#32, S-220) | the queue `pm_manager` and its patterns |
| Gates, the record, the review lane | `env.actuator`, `env.act`, `env.action`; #32's review lane for `propose` | the four `pm.*` actuators |
| The router | as it is: each tool an actuator, caller from the token, `env.mcp_policy` for first gates (S-205, S-206, S-218) | policies for the `pm` server's tools |
| The conversation | `desktop/server.py`, the Assistant view, `desktop.*` signals (S-206) | the manager answers there instead of the assistant |
| The companion | from `1f36971`: its Containerfile and start script (Claude Code pinned, tmux, own home), the gateway pass-through settings, the meter reading, the `task` actuator's `claude -p` call, the over-budget gate flip | rewritten for many workers and several runners |
| Kaggle | MetaSoar's `trials/kaggle/job.py` (push, wait, download, resume) | its status as a runner |
| The judge | Morphogen's `change` and `judge`, its reviewer agent | the `judge` worker kind |
| Claude Code | `--bg`, `agents --json`, `respawn`, `--resume --bg`, `-p --output-format stream-json`, `--max-budget-usd` | the supervisor around them |
| | | `014_portfolio.sql` and its logins; the portfolio MCP server and its HTTP API; the supervisor; `scripts/manager.sh` and `deploy/manager/`; the view module; `scripts/portfolio.py` |

**Build order.** Small steps, each checked before the next; each step is the owner's to start.

1. **Done here:** this design and the watch trial. Done when the owner has read it and answered section 10.
2. **The portfolio's tables and logins** (`014_portfolio.sql`, `scripts/db.py`, tests in `test_environment.py`), and
   `scripts/portfolio.py export|import`. Done when the tests show the manager's caller cannot set `done`, `class` or
   a worker's state or answer a decision, a worker cannot report for another, the supervisor cannot answer, and the
   files round-trip.
3. **The supervisor, for `local` workers:** watch and apply, with a worker's token and MCP config. Done when, from
   the command line with no manager, `env.act('pm.start', ...)` starts a background session in a worktree of a
   scratch repository that reports `done` with a branch; `claude stop` on it shows as `stopped`; a recorded log with
   the limit line gives `limited` and a respawn at the reset; a `pm.message` to a `blocked` worker continues the same
   session (or the design changes); and the gateway counts the worker's tokens (or the transcript does).
4. **The portfolio's MCP server behind the router.** Done when a start for a `client` project waits in Review and
   runs once approved, and a start for an `own` one runs at once.
5. **The manager session** (`scripts/manager.sh`, `deploy/manager/`). Done when, from the Assistant window, a status
   question is answered from the portfolio and a work request starts a worker, with no built-in tool in its
   transcript.
6. **The view** (`desktop/view-manager/`). Done when its three panes follow a live run and an answer in the inbox
   reaches the worker.
7. **Trial PM-1** (section 8). Done when it has run and its result is in `DECISIONS.md`.
8. **The judge step.** Done when a worker's `done` on a project with a Morphogen catalog goes through `morphogen
   change` before it reaches the inbox, and the verdict's author is never the worker.
9. **More runners,** one at a time as projects need them: `container` (done when a client-class project's worker runs
   in a container, its cap enforced), `kaggle` (done when a MetaSoar experiment runs from a chat request and its
   results file is the worker's ref), `scheduled` (done when the morning digest and one scheduled worker run from
   pg_cron).

## 10. Open questions for the owner

1. **Privacy:** the manager on Haiku sends your messages and the projects' summaries to Anthropic, as S-136 allowed
   for the companion. Recommended: yes, for this stream; the routing step moves to `fast` if PM-1's replay says it can.
2. **One agent to talk to:** should the manager take over the Assistant window (recommended), or run beside the
   assistant as a second conversation?
3. **Which projects are `own`:** recommended Substrate, MetaSoar, Morphogen and the kernel; anything for a client is
   `client` and every start there waits for you. Is Kaggle `free` within the week's 30 GPU hours (recommended), or
   always proposed?
4. **Workers' defaults:** Sonnet at low effort, at most three at once, one writer per project, a daily token budget
   per project (what number?). Workers on the host in auto mode with draft PRs only, as your sessions run today:
   acceptable, or should they start in containers?
5. **Cloud work:** leave cloud threads to Claude Code Projects (your github.com repositories only) and keep them out
   of the portfolio for now (recommended), or link Projects' threads into it later?
6. **Usage-limit resume:** resume automatically at the reset, one worker at a time (recommended), or ask first?
7. **Where the files-only mirror lives:** `portfolio/` in Substrate (recommended), or a repository of its own?
