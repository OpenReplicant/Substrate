# The personal assistant: a brief

Spec step 21, framed 2026-11-11 (S-80). Nothing here is built. No personal stream is read until every rule in
[PRIVACY.md](PRIVACY.md) has its check and the owner has turned a stream on.

## What it is

The same loop as the game player (spec section 10, "Environments"), pointed at the owner's own world. Each
personal stream is an **environment**:

- an observation comes in (a calendar change, later an email, a file, a note);
- a decision goes up the ladder of handlers (rules, a local small model, a local large model, the owner);
- an action goes out, and the next observation shows what it did.

The owner is the top rank. What they do with each proposal (accept, edit, redo, ignore) is its outcome. The
ladder learns from those outcomes, never from a model's opinion.

**Actions are proposals.** The assistant changes nothing in the owner's world on its own. It proposes ("move
the 3pm to Thursday", "decline: it clashes with the review"), and the owner accepts, edits or ignores it in
Workbench's review lane. A kind of action can become automatic only through a compile-down judged on held-out
weeks, and only for that kind, and each one is a map change the owner approves.

## First stream: the calendar

The calendar first because it is structured (times, people, titles), low in risk next to email, and easy to
score: did the owner accept the proposal, change it, or ignore it?

| | |
| --- | --- |
| Observation | an event added, changed or removed, and the day around it |
| Actions | propose: accept or decline an invitation, move an event, protect a block of time, flag a clash |
| Outcome | the owner's response to each proposal, and what the calendar shows a day later |
| Held out | whole weeks, never read while a compile-down is built |
| First ranks | a rule over the owner's stated preferences (from an interview), a local small model, a local large model, the owner |

How the calendar is read is a choice for the research skill (spec section 5), with the owner. The candidates
to look at first read from this machine, not through a cloud connector: an ICS export the owner drops in a
folder, or CalDAV from the calendar's own server. A connector run by another company would send the calendar
through that company, which the privacy rules forbid for content.

## Later streams

Email, messages, files and notes, each the owner's choice, each with its own privacy check first. Several
streams can feed one decision (the calendar and the inbox for one reply). They meet in the input a handler is
shown, so the ladder sees them.

## What it needs that does not exist yet

- Ollama on this machine with a small and a large local model, picked from leaderboards (S-75), behind the
  gateway (`OLLAMA_URL`).
- The environment slot (step 19) and episodes in the handlers plugin.
- A domain of its own in Workbench for the owner's personal items, readable only as PRIVACY.md says.
- An interview about the owner's preferences (the interview skill), so the first rule rank has something to apply.
