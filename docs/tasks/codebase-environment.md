# Task: the `codebase` environment: the agent works on its own code

**Model:** Sonnet for the tool search, Opus to build. **Needs:** `environment-package.md`. S-101: the work done
in these sessions is the first stream of tasks; other projects' tools are interfaced, not ported (S-99).

## Scope

1. **Tools, through the `research` skill** (`docs/choices/codebase-tools.yaml`): static analysis and code
   navigation that run with no model, permissive licence, one binary or container, JSON output or MCP. Lead:
   `yfedoseev/fossil-mcp` (read 2026-11-15: Rust, MIT or Apache-2.0, MCP over stdio, CLI with JSON and SARIF,
   a `check` command with exit codes; no release was listed on its page, so check the two-week rule). Search
   for at least two others. Trial each on this repository.
2. **Interface the pick** three ways, each small: as a tool the agent (and Claude Code, via `.mcp.json`
   through `scripts/harness.py`) can call; as a line in `scripts/check.sh` or a cell's `tests` (dead code and
   clones may not rise); as an observer whose call graph gives the map at code zoom (components and
   interfaces, `observed-ontology.md`'s generic form). It goes on the map as a reached component. The binary
   goes into `deploy/tools/Containerfile`, pinned, never on the host.
3. **Stream `codebase-tasks`**: an input is a chore in a repository (explain a failing check, find where
   something is defined, a small fix). Outcome: the repository's own checks, and what the person did with the
   result. Works on any repository named in the input, not only this one.

## Leave alone

Porting any tool's features. `repos/`. Anything that makes the environment work only on Substrate.

## Done when

The choice file records candidates, trial and pick; the picked tool answers through MCP in a Claude Code
session here and its findings on this repository are in the Knowledge Kernel citing its output; one chore has
gone up the stream's route and been decided; `scripts/test.sh` and `scripts/check.sh` pass.
