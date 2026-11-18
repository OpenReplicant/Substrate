---
name: build
description: Build toward a blueprint - close the gap between what the map says should be and what is, by a branch and a pull request that goes through the target's gate (Morphogen's verdict, a person, or both). Use when the owner or an agent asks for something to be built, fixed or improved in a repository Substrate works on, including Substrate itself.
---

# Build: from blueprint to observed, through the gate

1. **What is asked, against the map.** Read the blueprint (the spec, `map/blueprint/`) and what is observed
   (`map/observed/`, the code). The work is the difference. If the request is not in the blueprint, write it
   there first (the map skill), so the change has something to be judged against.
2. **The gate, from the base.** Read the target's policy as committed on its base branch: its `morphogen.yaml`
   (which cells may change, how better is measured), branch protection, any autonomy setting. Never change the
   policy, the judge's settings or its cases in the same change; a change to them is a change of its own, gated
   by the policy already in force.
3. **Build on a branch.** Work as you normally would; run the target's own checks. Your tests are for you: done is
   the gate's verdict, not your report.
4. **Propose.** Push and open a pull request saying what was asked, what changed, what you measured, and which
   blueprint entries it fulfils. Morphogen's check runs on it where the target has one. A person merges, or the
   policy's autonomy does; you do not merge past a missing or failed verdict.
5. **Update the map.** What you built moves into `map/observed/` with evidence pointing at the code; run
   `python3 check.py --stamp`.
