# Two "worse" agents that were not worse, and a case every run lost

Draft, 2026-11-16. Not published: the name it goes out under and whether it goes out are the owner's. Every
number is from the judge's evidence log (records 4 to 7) or from `DECISIONS.md` row S-110.

## The short version

Before trusting a judge to tell a better agent from a worse one, we checked that it could tell the same agent
from itself and from agents we had broken on purpose. Three things came out of four runs:

1. Two of the three agents we broke on purpose were not worse. One was slightly ahead.
2. Every score the judge had ever produced for us was one case low, on both sides, and nothing had said so.
3. The same unchanged agent scored between 0.396 and 0.458 from one run to the next. Any claim smaller than
   that gap is noise on this case set.

None of this needed a clever attack. It needed running the comparison instead of assuming its result.

## The setup

- **The task.** A question about a software package ("What licence does PyPI list for the Python package
  colorama?"), answered from what a registry says: PyPI, npm, crates.io, GitHub or the Hugging Face Hub. The agent can search, fetch a page and
  answer, in at most eight steps. Fetched pages are recorded, so a judged run replays them and never touches
  the network.
- **The agent.** One small local model (Granite 4.0 Micro, 3B) with tools, instructions and a notes file. The
  model is the same on both sides of every comparison.
- **The cases.** 48 questions with recorded answers. An agent that answers nothing scores 0. One that answers
  "yes" to everything scores 0.208.
- **The judge.** Morphogen. It checks out a base commit and a candidate commit, runs both in containers with
  no network, alternates their order from round to round, scores each run's output with the base's scorer in a
  separate process, and counts model tokens at a gateway outside the agent. A candidate passes only if its
  score beats the base's by a set margin with the sign test agreeing across rounds.

**What this set is not.** The 48 cases are open development cases that the agent's author could read. They were
good enough to ask "can the judge tell same from worse". They are not good enough to judge a real change, and
none was judged on them.

## The four runs

| Run | Candidate | Base correct | Candidate correct | Interval of the gain | Tokens | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | The same agent (a comment added) | 0.4375 | 0.4375 | -1.0 to 0.0 points | 193,688 to 192,413 | not better |
| 4 | Step limit cut from 6 to 2 | 0.458 | 0.479 | 0.0 to +8.3 points | 197,092 to 157,428 | not better |
| 6 | Instructions: answer from memory, read nothing | 0.396 | 0.396 | -2.1 to 0.0 points | 182,378 to 161,773 | not better |
| 7 | Answer "yes" to everything | 0.396 | 0.1875 | -20.8 to -20.8 points | 188,578 to 0 | not better |

Each ran five or six rounds. Scores are the median across rounds.

### Same against same: refused, as it should be

Run 5 is the check every judge should pass before anything else. Identical agents, identical score, and the
judge said "not better". A judge that passes an agent against itself some of the time will pass noise.

### The step limit: we expected worse and got cheaper

We cut the agent's step limit from six to two, expecting it to run out of steps and fail. It scored 0.479
against 0.458 and used a fifth fewer tokens. The judge still refused it, correctly: two of five rounds tied and
the gain did not clear the margin.

The lesson is about us, not the agent. We had labelled this candidate "worse" before measuring it. Had it been
used as the known-bad example in a check, the check would have been wrong and the judge blamed. A lower step
limit is a real candidate and may be a saving.

### The instruction the model ignored

We told the agent, in its instructions, to answer from memory and read nothing. Its score did not move at all:
0.396 against 0.396. Run by hand on eight cases, it fetched pages every time. While the tools are on offer, this
model uses them, whatever the instructions say.

So a whole class of change (rewording the instructions) does little for this model, and what it does is decided
by the tools it is given and the code around it. That is worth knowing before spending a week on prompts.

### The constant answer: the judge sees a real drop

The agent that says "yes" to everything fell from 0.396 to 0.1875, with the whole interval below zero in every
round. This is the one candidate that was worse, and the judge said so without doubt.

## The case every run lost

The constant "yes" agent is easy to score by hand: 10 of the 48 answers are "yes", so it should score 0.208. The
judge gave it 0.1875, which is 9 of 48.

The cause was a rule in the judge and a habit in our workloads meeting each other. The judge treats the last
JSON line a run prints as the run's report about itself, and does not pass it to the scorer. Our workloads
printed one JSON line per case and stopped. So the last case never reached the scorer, and counted as wrong, in
every judged run we had made.

It hit both sides alike, so no comparison was unfair. But every absolute score was one case low: 1 in 48 here,
and 1 in 7 on an earlier, smaller set, where it moved the number a great deal. An earlier figure we had quoted
was measured that way.

Two fixes followed:

- The workloads now end on a closing line, and the contract test for an environment checks that they do.
- The judge now refuses a run whose scorer saw a different number of cases than it holds answers for
  (Morphogen pull request 82). The scorer reports both counts. A short run by the candidate fails the
  candidate; a short run by the base stops the judgment, because the workload itself is broken.

The second fix also closes a cheat. Against a scorer that divides by the answers it saw, an agent that quits
before the cases it would get wrong looked perfect: 1.0 against the base's 0.62 in the test that now guards it.

## What the noise says

Across the four runs the unchanged base scored 0.4375, 0.458, 0.396 and 0.396. That is a spread of about six
points, or three cases out of 48, from nothing but the model's run-to-run variation.

On this set, then, a claimed gain of a few points means nothing, and a gain has to be near ten points before it
is worth a second look. Most changes people make to agents are smaller than that. The honest options are more
cases, a comparison made case by case instead of run by run, and saying before the run what the smallest
visible effect is. Those are the next changes to the judge.

## What we take from it

- **Check the judge on known answers first**: the same agent against itself, and an agent that is certainly
  worse. It takes an afternoon.
- **Measure the "known bad" example before calling it bad.** Two of ours were not.
- **Score one trivial agent by hand** and compare with what the pipeline says. That is how the lost case was
  found.
- **Know the noise before reading a gain.** Run the base against itself several times and look at the spread.
- **Keep the scoring outside the thing being scored**, and have it say how many cases it saw.

## What is still weak

- The cases were not held out. The same checks have to be repeated on cases the agent's author cannot read.
- Each run is one sample to the judge's statistics. That suits timing, not agent quality: the 48 cases
  inside a run are not compared one by one.
- On one machine, the agent's author can still reach the private cases. The judge has to run under another
  user or on another machine.
- One model, one task, 48 cases.
