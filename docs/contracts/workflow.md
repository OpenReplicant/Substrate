# Contract: the workflow field

Between **Substrate** (which holds who may approve what), **Morphogen** (which says what a verdict allows) and
the **Knowledge Kernel** (which records the approval). "Workflow" is the new word for approval policy; the
moderation queue is the new word for the review lane.

It is floor: `docs/archive/direction.md` puts "who may approve what" among the things only people change. This page
writes down what is already decided (S-25, S-37, S-51, S-74, S-94) and gives it one field. It changes no one's
authority.

Read from Morphogen at `52385af` (`project.py`: `autonomy`, `owner`, `lifecycle`, `Project.gate`), Workbench
(`wb.decision`, `api.decide`), spec section 7 ("who decides").

## The rule

State (claims, memories, outcomes, calls) is written freely, each write with its author. **Structure**
(anything that changes how a component behaves) lands only by its component's workflow.

## The field

Every governed component carries `workflow`, one of four names. A component without the field has `review`.

| `workflow` | Lands when | For |
| --- | --- | --- |
| `verdict` | Morphogen's verdict passes with `gate.decision: merge` | changes the owner has let land alone: none today |
| `verdict-and-review` | a passing verdict, then a person approves in the moderation queue, citing it | every governed component now (the model handler's prompt; next the router, recall's weights) |
| `review` | a person approves in the moderation queue; no verdict is possible or meaningful | the map, a new stream or handler, an action kind moving from `propose` to `free`, anything that reads a person's stream |
| `people` | a pull request the owner reviews; never a verdict from the thing changed, never an agent's approval | the floor: the judge and its rules (`morphogen.yaml`, scorers, drivers, cases), provenance, the record of calls, this field and its values |

## How each side holds it

| Side | Holds | Today |
| --- | --- | --- |
| Substrate | `workflow` on the component item, exported with the map | not yet a field; every component behaves as `verdict-and-review` or `review` by S-51 |
| Morphogen | per cell `owner` and `lifecycle` (from the catalog), and `autonomy: {<lifecycle>: merge|review}` in `morphogen.yaml`; `gate.decision` on every verdict | no `autonomy` key, so every pass says `review` |
| Knowledge Kernel | a decision in the queue: `open`, then `approved`, `declined` or `withdrawn`, with `decided_by`, `decided_at`, `note` | in use for the map's gaps |
| git | the landing itself: a merge to the trunk | the only gate that exists (direction, backlog) |

The mapping is one way: `workflow: verdict` on a component is true only if `morphogen.yaml` at the base commit
has an `autonomy` row giving that component's lifecycle `merge`. Substrate never reads `verdict` as permission
on its own; it reads `gate.decision` from the verdict. Since `morphogen.yaml` is outside every `change`, a
candidate cannot grant itself `merge`.

## Rules

1. **An approval names what it approves**: the verdict's `seq` and `hash` and the candidate commit. It is void
   for any other commit.
2. **No one approves their own change.** The proposer (the session or handler that made the candidate) is never
   `decided_by`. An agent with its own login may approve only where S-37's automation level lets it, and never
   for `people`.
3. **A lower rank recommends.** On an advisory stream a handler's answer about a decision is a recommendation
   recorded beside it; the decision is still a person's (S-76).
4. **Loosening is `people`.** Moving a component to a looser workflow, adding an `autonomy` row, or raising the
   automation level is the owner's decision, recorded in `DECISIONS.md`. Tightening is `review`.
5. **A fail needs no approval and gets none.** A refused change cannot be approved into landing; the way
   forward is a new candidate or, if the measure is wrong, a `people` change to the measure first.

## Check

For each landed change to a governed component: a `verdict` item with `verdict: pass` whose `candidate` is the
merged commit, and an approved decision citing its `seq` and `hash`, decided by someone other than the proposer.
`scripts/check.sh` can count the landings that lack one once the field exists; until then the check is by hand
at each merge to `main` (handoff, order item 7).

## Open

- **Self-approval is not enforced in code.** S-37 says the old kernel refused it (KK025); `api.decide` in
  Workbench today sets `decided_by` and checks only the editor role. Rule 2 holds by practice until the queue
  refuses a decision whose decider raised it. Needed before any agent login decides anything.
- **Nothing enforces `gate.decision`.** Morphogen records it and its skill follows it; git's merge is the real
  gate. The gate service in the backlog is what would enforce it, built when a second governed store exists.
- **The field itself** (a `workflow` property on `component`, exported as an annotation) is added in the task
  that first needs a value other than the default, most likely step 4's compile-down.
