# Privacy rules for personal streams

Written before any personal stream is read (spec step 21, S-80). Each rule has a check. A personal stream turns
on only when every check passes and the owner has turned that stream on by name. Until then the assistant
reads nothing.

| # | Rule | Check (to build before the first stream) |
| --- | --- | --- |
| P1 | **Nothing is read unless the owner names it.** Each personal source is listed by the owner in an uncommitted local file (as `observe.local.yaml` lists what may be observed), and is off by default. | a test that an unlisted source yields nothing, and that the file is gitignored |
| P2 | **Personal content stays on this machine.** It is stored only in this machine's Workbench, in a domain of its own, never in the repository, a log, a commit or an export. | a test that the map's export and every committed file carry no item from the personal domain; gitleaks before import |
| P3 | **Only local models see personal content.** A handler on a personal stream gets a gateway key allowed only the local provider (Ollama). OpenRouter's free models never see it: their providers may keep or train on prompts. | the gateway's contract test: a personal handler's key is refused for any non-local model |
| P4 | **Claude Code does not read the personal domain by default.** What Claude Code reads goes to Anthropic's API. The `claude-code` agent's Workbench role cannot read personal items unless the owner grants it, per stream. | a test that the agent's token gets nothing from the personal domain |
| P5 | **Secrets are never kept.** Everything read passes gitleaks before it is imported; a finding drops the item and says so. | the observer's gitleaks step, tested with a planted key |
| P6 | **Transcripts are off.** A personal stream keeps a call's answer, confidence, reason and cost, not its prompt or reply, unless the owner turns transcripts on for that stream. The gateway keeps no content at all (S-77). | a test that a personal stream's calls have no transcript by default |
| P7 | **Retention is bounded.** Raw items are kept for a number of days the owner sets (`ASSISTANT_RETENTION_DAYS`), then dropped; claims keep only what a decision needs, quoting as little as possible. | a timer job and its test: an item past retention is gone, its claims retracted |
| P8 | **The assistant proposes; it does not act.** No message is sent and no event changed except by the owner's acceptance, until a judged compile-down earns one kind of action (BRIEF.md). | a red-team test: a handler that acts without an accepted proposal is refused |
| P9 | **The owner can stop and forget.** Turning a stream off stops reading it; forgetting it deletes its items, calls and claims. | a test that forgetting a stream leaves none of its data |
| P10 | **Judging holds out whole weeks.** A compile-down is judged on weeks it was never built from (as step 13 holds out windows). | the idle tier's red-team test (step 20) covers personal streams too |

The owner decides what each stream may do. These rules are the **default flow policy for the `private` label**
(spec section 7, S-89): privacy is adjustable, because some of it cannot be kept on every machine or stream. The
owner may loosen a rule for a named stream or label; each loosening is a decision in the review lane, saying who,
when and why, and the rule's check then tests the policy as set rather than the default.
