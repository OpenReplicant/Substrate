# Harness trial (S-172): existing agent harnesses for Substrate's agent slots

Written before any candidate was run. M-17's skill gate moves to the model endpoint (an OpenAI-compatible proxy or
a Bifrost plugin in front of the local models), so a harness no longer needs a seam of its own: any harness that
talks to the gateway can fill a slot, and the gateway still counts its model calls.

## Slots

1. **Worker**: multi-step tasks on the local slow model (`local/slow`, Inkling 2 Mini on the CPU, about 7 tok/s out,
   about 26 tok/s reading a prompt, 16k context), headless, one task at a time from the `worker_loop` queue.
2. **The fast layer's tool use**: the 1.7B (`fast/fast`, GPU, 32k context) behind the voice loop. The voice loop
   itself stays ours (latency, streaming into speech, barge-in); a harness fits here only if it adds little latency.
3. **Companion, author, judge**: Claude Code on the owner's login today (the companion, S-136); a harness could take
   the author's or judge's loop if it fits.

## The need (every candidate is tested against all of it)

| Need | How it is checked |
| --- | --- |
| Talks to our gateway: OpenAI-compatible base URL and key (`Authorization: Bearer`; the Responses API and the Anthropic Messages API also work through Bifrost, checked 2026-11-22) | a case passes through the gateway with the trial's key |
| Headless: one task from the command line, a result we can read (JSON or a final message) | the runner reads it |
| MCP client over stdio | case `mcp`: a stub MCP server's tool is called and its answer used |
| Shell with rules: read-only commands allowed, destructive ones refused or held, headless | cases `shell` and `refuse` |
| Files in a workspace | case `file` |
| Small enough a prompt for the slow model's 16k context | its prompt tokens per call, from the gateway's log |
| No telemetry by default | it runs on a network that reaches only the gateway and a recording proxy; any other call is logged or fails |
| Licence permissive (or GPL only in its own container, S-146); a release at least two weeks old, pinned; in a container | registry facts, quoted in the results |

## Cases

- `file`: "Create the file trial.txt containing the word ok, then read it back and tell me what it says." Pass: the
  file holds `ok` and the answer says ok.
- `shell`: "How much free disk space is there on /? Use a shell command." Pass: a `df` (or similar) ran and a size is
  in the answer.
- `refuse`: "Delete the file trial.txt." with the harness's rules set to refuse or hold `rm`. Pass: the file still
  exists afterwards.
- `mcp`: "Use the add tool to add 2 and 3, and tell me the result." with `stub_mcp.py` as an MCP server. Pass: the
  stub logged the call and the answer says 5.

Each runs first on `fast/fast` (quick, to test fit), then the shortlist on `local/slow` (the worker's real model).
Results: one line per candidate and case in `.state/trials/harness/summary.txt`.

## Parked (2026-11-22)

Before any case ran, the owner chose another route: our own runtime (pgmq, the environment's gates, a process and
container orchestrator) with MCP as every component's interface, our own agent loop on it, and existing harnesses
(Claude Code for the subscription, others) run as agent instances behind the same contract rather than conformed to
one by one. What stays useful from here: the need above, `candidates.json` (the entity list, in the catalog skill's
shape, for the kernel), the isolated network (`net.sh`), `stub_mcp.py`, and the finding that the gateway serves the
Chat Completions, Responses and Anthropic Messages APIs with a Bearer key.
