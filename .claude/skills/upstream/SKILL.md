---
name: upstream
description: Contribute a fix or improvement found while running the substrate back to Morphogen (or another project in repos.yaml), by branch and pull request in that repository; also applies prepared patches from upstream/. Use when a problem's cause is in repos/morphogen, or when the owner asks to open, update or land an upstream PR.
---

# Contribute upstream

Each project in `repos.yaml` is a full clone in `repos/` (`repos.local.yaml` when the owner points one at
another forge); today that is `repos/morphogen`. A fix to one belongs there, not in substrate.

**Any forge** (S-25). The canonical repositories are on GitHub, but a clone's `origin` may be a Forgejo, Gitea
or GitLab mirror or fork. Work out which from `git -C repos/<repo> remote get-url origin` and use that forge's
way of proposing a change: on GitHub a pull request (`gh`), on GitLab a merge request, on Forgejo or Gitea a
pull request. When no CLI for that forge is set up, push the branch and give the owner the link the push prints
(each of these forges prints one), or the forge's compare page. A change accepted on a mirror still has to reach
the canonical repository; say where it landed and what is left.

## Before changing anything

1. Read that repository's `CLAUDE.md` and follow it there. Morphogen:
   red team first for any change to the judge, an A/A check after statistics changes, the plugin installed
   from GitHub.
2. `git -C repos/<repo> status`: start from a clean tree. Stash or branch anything there, and say so.
3. `git -C repos/<repo> fetch origin && git -C repos/<repo> switch main && git -C repos/<repo> pull --ff-only`.

## Make the change

1. Branch: `git -C repos/<repo> switch -c <short-name>`.
2. A prepared patch: `git -C repos/<repo> am ../../upstream/<repo>/<file>.patch` (from `repos/<repo>`, the
   path is relative to it), then check it still makes sense on today's main.
3. Write or change the code, with its test first where the repository expects one.
4. Run the checks that repository's `CLAUDE.md` lists for what you touched, and substrate's
   `scripts/check.sh` to prove the fix where it was found. Name the engine you tested with.
5. Commit in that repository's style, with the attribution lines your harness asks for.

## Open the PR

1. `git -C repos/<repo> push -u origin <branch>`. If the owner has no push access there, push to their fork
   and open the PR from it.
2. Open the pull or merge request on that forge (`gh pr create` on GitHub): what broke, where it was found (substrate, which step), the fix, the
   checks run. Link the substrate commit or issue that found it.
3. Delete the applied file from `upstream/<repo>/` in substrate, and commit that.
4. While the PR is open, `repos/<repo>` stays on that branch only if substrate needs the fix to run; say so
   in the substrate commit. After it merges: `switch main`, `pull --ff-only`, delete the branch.

## When the fix lands

Update `repos.yaml`'s `checked` commit to the main commit substrate was tested against, run
`scripts/check.sh`, and commit.

## Prepared now

Nothing waits in `upstream/`, and no upstream PR is open from here.
