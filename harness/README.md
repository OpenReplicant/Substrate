# The harness: Claude Code with kernel, Morphogen and the gateway

Three connections, each made once per project (S-03, S-04).

## 1. Kernel: memory and the operator's tools

`kk up PROJECT` (run by `scripts/up.sh`) merges kernel's MCP entry, skill and hooks into the project:
`.mcp.json`, `.claude/skills/knowledge-kernel/`, `.claude/settings.local.json` (kernel `docs/harness.md`).
Approve the `kernel` MCP server when Claude Code asks. The agent then sees the four memory tools; use
`kk up --profile operator` for every tool.

## 2. Morphogen: the judge

Install it from GitHub, never from `vendor/morphogen`: a plugin installed from a local checkout runs from
that checkout, so the judge would be the candidate being changed (Morphogen's CLAUDE.md).

```text
/plugin marketplace add OpenReplicant/Morphogen
/plugin install morphogen@morphogen
```

The substrate's own map is already a Morphogen project: `morphogen.yaml` reads `catalog-info.yaml`.

## 3. The gateway: every model call measured outside the agent

In Bifrost's UI (http://127.0.0.1:8090/ by default) add the Anthropic provider and create a virtual key
allowed to use your models. Then choose one, per Bifrost's `docs/cli-agents/claude-code.mdx`:

- **A virtual key with a provider API key in Bifrost:** copy `settings.gateway.example.json` into the
  project's `.claude/settings.local.json` (merge its `env` with what `kk up` wrote) and fill in the key.
- **Your claude.ai subscription, governed by Bifrost:** keep your Claude login, set
  `ANTHROPIC_BASE_URL` to the gateway, and send the virtual key in the `x-bf-vk` header; follow that
  document's subscription section.

Check it: one Claude Code prompt, then `curl -s http://127.0.0.1:8090/metrics | grep bifrost_cost_total`.

Unset any `CLAUDE_CODE_USE_*` variable: each routes Claude Code to a cloud provider instead of
`ANTHROPIC_BASE_URL` (Bifrost's same document).
