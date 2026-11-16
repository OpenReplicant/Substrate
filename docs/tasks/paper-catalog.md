# Task: the paper catalog: amass, then present

**Model:** the largest for this design and the review; Sonnet to build the harvest (plain code, no model in
it); Haiku for page fetches. **Needs:** `first-package.md` (done). **Decided by:** S-111. This is the first leg
of the project; `papers-environment.md` (reading with a model, then reproducing) becomes legs two and three
and works from this catalog's shortlist instead of papers saved one at a time.

## The question

What has been published about agent harnesses and about cognitive designs with language models, which parts
of it come with code, and which could be tested here cheaply? Answered as data anyone can search, where every
value opens to the page it was read on.

## Scope

1. **Sources on the map.** Each registry the harvest reads (arXiv, OpenAlex and whichever others the survey
   confirms) is a `component` in system `sources`, with how to query it, its limits and the licence of its
   metadata, read from its current docs (rules 1, 3 and 8). No source is used before it is there.
2. **Objects**, in the package's plugin:
   - `paper`: its identifiers (arXiv, DOI, the registry's own), title, authors, date, venue, abstract where
     the licence allows, citation count, code repositories, licence. Each value is a claim citing the
     registry that gave it, so two registries that disagree both stay visible.
   - `listing`: a curated list, a survey or a digest that names papers: where it is, who keeps it, its
     licence, when it last changed, how many papers it names.
   - A paper is **listed in** a listing, under the heading it sat under. The heading is the list keeper's
     claim about what kind of thing the paper is; headings are gathered as they are, and are not yet a
     taxonomy of ours. How many listings name a paper is a signal, as is who.
3. **The harvest**, in `packages/papers/`: the sources are the environment's sensors (S-102: readings encoded
   into claims) and the first agent is one handler with no model. Two passes, each able to stop and resume:
   listings into the papers they name (identifiers parsed from links); identifiers into metadata from the
   registries. A fetch is recorded (URL, date, body hash) as `lookups` does. It keeps to each source's stated
   rate, sends a generic client name, and a second run over unchanged sources writes nothing.
4. **Presenting.** A view in the shell: papers with filters for topic heading, listing count, citations,
   date, has code, licence; a paper opens to its claims and the listings that name it.
5. **The cheap-test flag.** `testable` on a paper, set by rule from data only: it has a repository, the
   repository's licence is permissive or LGPL, and the repository is not archived. Whether its method fits a
   slot here and runs on a small model needs reading, so that part is filled in leg two. The flagged papers,
   most-listed first, are the queue for reading.

## Not in this leg

A model reading papers; stated claims quoted from a paper's text; writing a method as a candidate; a taxonomy
of our own; full text (kept only where a licence allows, and not needed yet).

## Running it somewhere else

The harvest is started the one way a package is (`PACKAGES` in `.env`) and needs nothing but outbound HTTPS
and the store, so a second machine that runs the stack can run it all day. Whether to rent or borrow one is
the owner's decision; nothing here may depend on which machine it is, and no key of the owner's goes to a
machine without their say.

## Leave alone

`repos/morphogen`. `packages/lookups` (the parked routine stays in its worktree). Workbench's core: types and
the view come from the package's plugin.

## Done when

- The registries used are components in system `sources`, and `scripts/map.sh export` is committed.
- One run from an empty store prints how many listings, papers and listed-in relations it wrote, and how many
  papers have a repository and are `testable`; a second run prints zeros.
- A paper named by two listings is one item with two listed-in relations (a test on recorded pages).
- Every value of a sample paper opens to its source through `get_item`.
- The view lists the papers with the filters above.
- `scripts/check.sh` passes.
