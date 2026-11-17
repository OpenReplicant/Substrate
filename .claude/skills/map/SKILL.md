---
name: map
description: Take a thing apart into its parts, the roles each part plays and the interfaces that make parts interchangeable, and write it into the store with evidence - any thing, software or not (a codebase, this machine, a bicycle, a team, a process). Use when the owner asks what something is made of, how its parts work together, what could be swapped or changed, or before cataloging alternatives for a part (the catalog skill).
---

# Map: what a thing is made of, and what makes its parts interchangeable

A map is statements in the store (S-139), through its MCP tools (`mcp__store__*`): a **whole** *has part* a
**part**, qualified by *object has role* the **role** the part plays there; a role *requires interface* the
**interfaces** anything filling it must provide; a part *provides interface* them. Everything you write is your
claim: it enters at normal rank and cites you, and the owner can prefer or deprecate it.

## 1. Find the whole, and the question

`search` before `create_item`, always: `create_item` also answers with similar items already there. Ask what the
map is for (what might change, what should get better) if it is not said: it decides how deep to go. Map to that
depth and stop; a part nobody would change needs no parts of its own.

## 2. Parts and roles

For each part: find or make it, then `say` *has part* (`has-part`) on the whole with the qualifier
*object has role* (`object-has-role`). The role is what the part does there, named so another part could do it
("drivetrain", "the store's embedding model", "bookkeeping"), an item made with `instance_of: role`. One part can
play several roles; say each.

## 3. Interfaces: what makes parts interchangeable

On each role, `say` *requires interface* (`requires-interface`); on each part, *provides interface*
(`provides-interface`). An interface is what crosses the boundary, named exactly enough to check: an API and its
version, a protocol, a file format, a socket size, a skill set, a schedule. Make each with `instance_of:
interface`. Two parts are alternatives when both provide everything the role requires (`alternatives` lists
them), so an interface named loosely ("an API") makes everything look interchangeable.

## 4. Evidence

Every `say` carries `evidence`: the source (`file:path`, an `https://` URL), where in it (`L10-20`, `p3`) and the
quoted text. Read the thing itself (code, config, a running process, a manual) rather than describing it from
memory; what you cannot cite, leave out or ask about. What a person tells you is theirs: quote them with the
conversation as the source, and say so in `note`.

The quote is the source's text at that locator, not an excerpt: quote the whole line or range (`L13`, `L10-12`),
and quote it the same way every time you cite it. A different quote at the same locator reads as the source
having changed: it supersedes the earlier span and flags every statement that cited it.

## 5. Goals

If the owner says what better means, put it on the whole: *has goal* (`has-goal`) a goal (`instance_of: goal`)
with *metric* (how it is measured, in words a judge could apply) and *target* (a quantity). Measurements and
verdicts come later, from trials and a judge (the catalog skill).

## 6. Check

`read` the whole's page; `path` from the whole to an interface; `violations` for the whole and its parts (a role
named where an interface belongs shows up here). Tell the owner what is mapped, what was left out and why, and
what you are unsure of. If you got something wrong, `deprecate` your own statement with the reason, and say the
right one.
