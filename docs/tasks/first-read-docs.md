# Task: what a newcomer reads first says what is true now

**Model:** Sonnet. **Needs:** nothing; do it in the same session as `04-rename-pass.md`, before it, since both
edit README and the skills. From `docs/readiness.md`, walk 1: findings 5 (the wording half), 6, 7, 10, 12, 16,
17, 18, 19.

## Scope

1. **The paused plan** (6, 7): the SessionStart hook's fresh-clone message (`scripts/spec.py`), the setup
   skill's "Afterwards", the build-out skill's trigger, `up.sh`'s closing line and README's "sessions here work
   through the plan" each say the plan is paused and point to `docs/direction.md` when `docs/build.yaml` has a
   `paused:` line. The build-out skill checks for the line first and stops.
2. **Ports** (5): the setup skill stops offering another port for 8080 until `second-checkout.md` adds one.
3. **Another system's details** (12): README says `observe.local.yaml`, as the interview skill and `CLAUDE.md` do.
4. **The services** (17): every list of the core stack names all seven, as `check.sh` does.
5. **Download size** (10): README says how much the first run downloads (about 7.5 GB of images, then the models).
6. **Without Claude Code** (16): a short README paragraph: the shell, `observe.sh`, `business.sh import`,
   `trace.sh`; and `business.sh` in `CLAUDE.md`'s command list.
7. **Notes for outsiders** (18): `CONTRIBUTING.md` (changes to Morphogen go upstream, `scripts/check.sh`,
   decisions as rows) and `SECURITY.md` (how to report a way past the judge or a leak). Ask the owner for the
   contact to name; leave a clear placeholder if there is no answer.
8. **Neutral examples** (19): the interview example uses a made-up person; generic files say "a GPU".

## Files to touch

`README.md`, `CLAUDE.md`, `.claude/skills/setup/SKILL.md`, `.claude/skills/build-out/SKILL.md`,
`scripts/spec.py` (the message text and the `paused:` check only), `scripts/up.sh` (its closing message),
`plugins/substrate/INTERVIEW.md`, comments in `streams.yaml` and `deploy/compose.nvidia.yaml`,
`CONTRIBUTING.md` and `SECURITY.md` (new).

## Leave alone

`docs/spec.md` and `docs/build.yaml` (`spec-rewrite.md`). Behaviour of any script beyond the messages named.
`DECISIONS.md` rows. Positioning: say what Substrate is, not what a client is offered.

## Done when

On a tree with no `.env` (simulate: `python3 scripts/spec.py hook` with the file moved aside in a copy, never
the real one), the hook's message does not mention the build-out; `git grep -n "build-out"` shows every mention
is conditional on the plan not being paused; `scripts/test.sh` and `scripts/check.sh` pass.
