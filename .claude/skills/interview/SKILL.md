---
name: interview
description: Interview a person about a system - one that exists, one they want, or a change to substrate itself - and put what they say on that system's map in Workbench as their own cited claims, with questions drawn from the map's gaps and thin parts. Use when someone says "map my ...", "interview me", "I want to build ...", "plan ...", "change substrate so ...", at a first session, or for spec step 8.
---

# Interview

Most of what a system is *for* lives in someone's head. This skill gets it onto the system's map as claims that
quote the person, so it can be checked against what runs and acted on. Read `plugins/substrate/INTERVIEW.md` (the
transcript format) and `plugins/substrate/MAP.md` (the map) first.

## 1. Which system, and how far

Ask, in one message, and recommend where you can:

- **Which kind.** A system that exists (a machine, a stack, a repository), one they want built, or a change to
  substrate itself. The loop is the same; where you start differs (section 3).
- **Its name**, for its domain on the map: short, lowercase (`rig`, `shop`, `home-lab`).
- **Scope.** What you may read, and what you may not. Read nothing beyond what they name. For an existing system
  on this machine, write what they allowed into `observe.local.yaml` (gitignored; same keys as `observe.yaml`:
  `env_files`, `claude_code`, `http`, `commands`, paths may start with `~`). Settings are kept by name, never by
  value, whatever the file.
- **Where its map may go.** It stays in Workbench. Never export it into this repository (`scripts/map.sh export`
  refuses); a path they name, or `.state/maps/`, only if they ask.

## 2. Start the transcript

Create `.state/interviews/<system>/<date>-<topic>.md` with the front matter (system, person, interviewer, date,
scope) and tell them the path: it is theirs to read and correct. Then, for every turn:

- a `## <n>. <topic>` heading, your question as `**claude-code:** ...`, and their answer as `**<person>:** ...`,
  **copied exactly as they typed it**. Never tidy, shorten or paraphrase an answer line; only their words go
  after their name. If they correct themselves, the correction is a new turn.
- If they paste something that looks like a secret, do not copy it; write `[removed: looked like a secret]` and
  tell them. `scripts/interview.sh` refuses to read a transcript gitleaks flags.

## 3. Ask from the map, one question at a time

Before each question, look at what the map already knows (Workbench MCP: `open_decisions`, `list_items` type
`component`, `get_item`, `search`) and ask about what is missing or thin. Never ask what you can observe.

- **A system that exists:** run `scripts/observe.sh` first (with their `observe.local.yaml`). What runs and no
  part claims is an `undeclared` gap; start there: "what is this for, and whose is it?" Then each part's purpose,
  who depends on it, what would break without it, what good looks like.
- **A system they want:** start from what it is for and for whom; then its parts; for each part, what it provides
  and needs, and **how you would know it is running** (that becomes its `observed-as`, so drift lists every part
  not running yet: that list is the build plan); then what "better" means for the parts that should improve
  (a measure Morphogen can judge).
- **A change to substrate:** what should be different and why; which parts it touches; how they would know it
  worked. The change lands on substrate's own map (its export is committed; map changes are the owner's
  decision).

Keep questions short and concrete, offer your best guess for them to confirm or correct ("It looks like X is
your backup volume. Is that right?"), and stop when they want to stop.

## 4. Put it on the map

- **A part they name that the map lacks:** create it (`save_item`, type `component`: `kind`, `type`, `system`,
  `owner`, `description`, `annotations`), as yourself; that is your claim that it exists. A Domain entry for the
  system and a System entry for each group of parts come first.
- **What they said about it:** a statement in the transcript's `## Statements` block, each one with the entry
  (`item: component:<slug>`), the `field` (a component field, or `annotations:<key>` such as
  `annotations:substrate.dev/intent`), the `value`, the `turn`, and a `quote`: words they actually said in that
  turn, exactly. A statement whose quote is not theirs is refused.
- **Links between systems** are fields too: the machine's `podman` is what substrate's `runtime` `depends_on`,
  for instance. Each is a claim like any other.

Then run `scripts/interview.sh`. Each statement that stands becomes **their** claim, quoting them, beside the
map's value. Where it differs from the map, the difference goes to the review lane. Fix what was refused (an
inexact quote) and run it again. Where what they said and what was observed disagree, ask them; their answer
decides which side changes (`decide`), and you make the change.

## 5. Close

Say what is now on the map (entries, statements that stand, gaps open), what you could not ask, and the one gap
you would close first, with how its change would be judged (`morphogen change` for a fix that claims no
improvement; a verdict with a measure for one that does). Ask before doing it.
