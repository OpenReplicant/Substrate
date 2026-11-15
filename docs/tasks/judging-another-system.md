# Task: judge a change to a system that is not Substrate

**Model:** the largest for the design (one contract page), then Opus to build it. **Needs:** walk 2 of
`client-readiness.md` (a second system on the map), and two decisions of the owner's below. From
`docs/readiness.md`, walk 3: findings 3.1 to 3.7. Today a second system can be mapped but not judged.

## Scope

**Design first**, as `docs/contracts/system.md`: what Substrate holds per system (a domain), and what stays in
that system's own repository. The page settles:

1. **Where a system's files live** (3.1, 3.6): its `morphogen.yaml`, its map's export and its evidence log
   are in its own repository; Substrate reads them from a root recorded per domain. Nothing of it is written
   into this checkout.
2. **Verdicts by system** (3.2): a verdict is keyed by its log (the domain and the sequence number), and an
   extractor run retracts only verdicts of the log it read. Until this is built, `scripts/verdicts.sh` must
   never be pointed at another log: doing so withdraws Substrate's own verdicts.
3. **Streams and keys by system** (3.3): a system's streams are declared with the system, not in this
   repository's `streams.yaml`; the gateway gives each of its handlers a key.
4. **Cases by stream** (3.5): held-out cases are cut from any stream's decided inputs, named by domain and
   stream, written outside both repositories.
5. **Gaps carry their system** (3.7): observed items and gaps have a domain, and the moderation queue can be
   read one system at a time. Walk 2 confirms whether this bites.
6. **Counting calls** (3.4): see the owner's decisions.

**Then build**, smallest first: 2 (it guards against losing verdicts), 5, 1, 4, 3.

## The owner's decisions

- **Must a client's system send its model calls through this gateway to be judged?** Recommended: yes for
  anything judged on cost, with a key per judged system; a system judged only on outcome and time needs no
  gateway. The alternative is trusting the client's own usage records, which the candidate could reach.
- **Where does a client's map live when the work is for them?** Recommended: in the Knowledge Kernel on the
  machine doing the work, exported only to the client's repository (`scripts/map.sh export DOMAIN FILE`
  already refuses to write here).

## Files to touch

Design: `docs/contracts/system.md`, `DECISIONS.md`. Build: `plugins/substrate/substrate_plugin.py` (the
`morphogen` extractor, drift's matching), `plugins/substrate/types/verdict.json`, `scripts/verdicts.sh`,
`scripts/judged.py`, `scripts/gateway.py` (keys), `plugins/substrate/MAP.md` ("judging another repository"),
tests beside each.

## Leave alone

`workbench/`: if a fix seems to belong there (retracting within a scope), it is a general feature with no
word of Substrate in it, or it is not done there. `repos/morphogen`: one Morphogen project per repository is
its design. Substrate's own verdicts, cells and held-out cases.

## Done when

Design: the page is written and the owner has answered the two decisions. Build: a test loads two evidence
logs for two domains and neither run withdraws the other's verdicts; a gap raised for the second system
carries its domain; `scripts/test.sh` and `scripts/check.sh` pass; the paper walk of `client-readiness.md`
walk 3 is redone and each "it cannot" is gone or has a reason to stay.
