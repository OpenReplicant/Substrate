# Interviews

An interview puts what a person says about a system onto its map as **their** claims, each quoting them. The
`interview` skill (`.claude/skills/interview/SKILL.md`) runs it; this is the format and what happens to it.

## The transcript

One Markdown file per sitting, in `.state/interviews/<system>/<name>.md`. It is gitignored: what someone says
about their system is theirs. The person can read and correct it at any time.

~~~markdown
---
system: rig                 # the domain on the map this interview is about
person: pete                # who answers: their statements are attributed to them
interviewer: claude-code
date: 2026-11-09
scope: this machine's Claude Code setup; nothing in ~/Documents
---
## 1. What it is for
**claude-code:** What is this machine for?
**pete:** It's my dev box. I build substrate on it.

## Statements
```yaml
- {item: component:rig, field: description, value: "The owner's dev box, where substrate is built",
   quote: "It's my dev box. I build substrate on it.", turn: 1}
```
~~~

- **Turns** are `## ` headings; the first word of the heading (`1`, `Q3`) is the turn's id.
- **Who said what:** lines `**<name>:** words`; a long answer may go on over several lines. Only the lines after
  the person's own name are theirs.
- **Statements** are a fenced YAML list under `## Statements`: the map entry (`item: <type>:<slug>`, the type
  `component` if left out), the `field` (a field of that type, or `annotations:<key>`), the `value`, the `turn`
  and the `quote`.

## What happens to it

`scripts/interview.sh` runs gitleaks over `.state/interviews` (a hit stops it), then `substrate:interview`
(`substrate_interview.py` reads; `substrate_plugin.py` records):

| A statement | Becomes |
| --- | --- |
| whose quote is the person's own words in that turn (case and line breaks aside), about an entry that stands | the person's claim on that field: author the person, run the extractor's, source the transcript, the quote and its line. It sits **beside** the map's value and never overwrites it |
| that differs from what the map says | the above, and a gap in the review lane: "pete said X; the map says Y". Deciding it changes the map, or leads to asking again |
| whose quote they did not say there (or the interviewer said), or that names nothing on the map | refused and raised as a gap, never recorded |
| taken out of the transcript later | retracted on the next run |

Workbench does this generically (migration 012: `wb.state_claim`, `ctx.state`): any source that quotes someone
can record what they said as their claim without writing over the item, and the run still says which extractor
read it.
