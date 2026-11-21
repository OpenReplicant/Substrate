# Spot-check of three research catalogs

Method: random.seed(7), random.sample over each file's `entries` list (6 per file). Main source URL(s) fetched with WebFetch on 2026-11-21 and compared with the catalog fields: URL, licence, agent connection, dates/versions. Catalogs were not edited.

## game_envs.yaml

- game_envs.yaml | MineDojo | confirmed | Licence MIT (code), CC BY 4.0 / CC BY-NC-SA 3.0 for data, as stated. Gym-style Python interface (`minedojo.make`, `reset`/`step`) as stated. No version or date on the page; 34 commits, matches.
- game_envs.yaml | MineRL | confirmed | Licence not named on the page (entry says unknown, correct). Gym-style Python package, v1.0, 17 June 2024 data-mirror notice all match.
- game_envs.yaml | OpenRA | confirmed | GPL-3.0, Red Alert / Tiberian Dawn / Dune 2000 mods, Lua mission scripting, no bot API on README: all match.
- game_envs.yaml | Factorio Learning Environment (FLE) | confirmed | Licence not named (entry says unknown, correct). Agent writes Python programs run through a REPL; `fle cluster start` with Docker; 887 commits: match. Page does not mention RCON (entry says RCON is in deepwiki, not read; consistent).
- game_envs.yaml | Dota 2 bot scripting | confirmed | docs.moddota.com Lua API matches (GetBot, Action_ / ActionPush_ / ActionQueue_ / ActionImmediate_). Differs: the moddota page does not describe a bots folder under vscripts (the entry cites the wiki snippet for that, which was not read); no licence or terms on the page.
- game_envs.yaml | Google Research Football | confirmed | Repo archived by owner on 19 Aug 2026 (entry matches). Licence not named (entry says unknown, correct). Environment API and multi-agent / external bot player types match.

Count, game_envs.yaml: 6 picked, 6 confirmed, 0 wrong, 0 couldn't check.

## npc_mods.yaml

- npc_mods.yaml | TALKER (STALKER Anomaly / GAMMA) | confirmed | MIT; Ollama, OpenRouter/OpenAI direct keys, LLM-API-Key-Proxy; hold-to-talk STT via TALKER-Mic; gemini-proxy marked NOT IMPLEMENTED; no version or dates; 216 commits. Memory persistence not stated on the page, consistent with the entry's "no persistent memory described".
- npc_mods.yaml | Smart Villagers AI | confirmed | Apache-2.0; OpenAI-compatible, Ollama, LM Studio presets; TTS via Simple Voice Chat; release smartvillagers-neoforge-26.3-2.0.0.jar dated Oct 25, 2026; client and server. Matches.
- npc_mods.yaml | LoraCore | confirmed | MIT; OpenAI key required; API URL changeable; Experimental; client & server ambiguous. Date note: the entry's "Jul 17, 2026" matches CurseForge "Last Update", but the same page says "Updated 4 months ago", which does not agree. Entry could say so.
- npc_mods.yaml | AI Character Engine (ai-character-engine) | confirmed | MIT; Ollama only (phi3 example); Character / Conversation classes; get_conversation_history(limit=10); 5 commits, 6 stars, 2 forks. Python library, not an engine plugin: matches.
- npc_mods.yaml | Mantella Fallout 4 VR ESP (companion to Mantella backend) | confirmed | MIT; F4SE, SUP F4SEVR, Version Check Patcher required; backend is a separate repo; 20 commits, no releases. Matches.
- npc_mods.yaml | SkyrimNet | confirmed | README says "not open source"; LICENSE text not shown (entry says unknown, correct). OpenRouter / OpenAI-compatible, LM Studio, Ollama, KoboldCpp, llama.cpp; paid Fateless tier needing Beta29 or later; 1,068 commits; no release date. Matches. Memory and action claims are the vendor's own (entry's "fetched" status is consistent).

Count, npc_mods.yaml: 6 picked, 6 confirmed, 0 wrong, 0 couldn't check.

## control_interfaces.yaml

- control_interfaces.yaml | Godot MCP (yanhuifair) | confirmed | AGPL-3.0; stdio default, SSE /sse and Streamable HTTP /mcp on 127.0.0.1:3000; plugin TCP 9876; runtime bridge 9877; 140 editor and 11 runtime tools; GODOT_MCP_TOKEN; 72 commits. Differs only in detail: the page lists 386 tools in total and its changelog example is inconsistent (1.12.16 vs 1.12.18); the entry's version is the "What's new" entry.
- control_interfaces.yaml | resonite-mcp (sandraschi) | confirmed | MIT; v1.1.0, ResoniteLink protocol 0.13.1; stdio via `python -m resonite_mcp --stdio`; dashboard on port 10978; no auth described; changelog dated 2026-09-02. Matches.
- control_interfaces.yaml | unreal-mcp (runreal) | confirmed | MIT; `npx -y @runreal/unreal-mcp`; Unreal Python remote execution, `editor_run_python`; UE 5.4+; bind 127.0.0.1; full-editor-access warning; 24 commits, no releases. Matches.
- control_interfaces.yaml | Steam Input (virtual Xbox pad and API) | confirmed | Overlay injects an emulated Xbox device on Windows, driver on macOS/Linux; no statement that third-party programs can inject through Steam; no anti-cheat statement (only a nav link); no date or licence on the page. Matches.
- control_interfaces.yaml | Resonite official API (SkyFrost) | confirmed | Page marked "heavy WIP", no support or guarantees; REST at api.resonite.com; SignalR hub; UID and TOTP headers; token lifetime 30 days with rememberMe, 24 hours otherwise; no avatar or world control; no bot rule. Matches.
- control_interfaces.yaml | FluxMcp (ProtoFlux MCP mod) | confirmed | MIT; archived 10 Mar 2026; TCP listener with bind address and port settings; README says the feature is now official via ResoniteLink. Matches. Page shows no version number, as the entry says.

Count, control_interfaces.yaml (picked entries): 6 picked, 6 confirmed, 0 wrong, 0 couldn't check.

## Policy quotes (control_interfaces.yaml)

- control_interfaces.yaml | vrchat-osc, policy: Terms section 12 | confirmed | Section 12 bars modification and circumvention of the Platform. Matches the entry's paraphrase.
- control_interfaces.yaml | vrchat-osc, policy: Terms 13.2(i) | confirmed | The phrase "in a manner inconsistent with individual human usage" is in 13.2(i). Matches.
- control_interfaces.yaml | vrchat-osc, policy: Terms 13.3 | confirmed | 13.3 covers anti-cheat and "modified clients" ("Mods"). Matches.
- control_interfaces.yaml | vrchat-osc, policy: "Terms section 13.2 ... prohibits any robot, spambot, spider, crawler, scraper ... or any engine, software tool, agent, device or mechanism not provided by VRChat" | wrong | The substance is in the Terms, but the clause is 13.2(j), not 13.2. The entry cites the introduction of 13.2 for it. Correct the pointer to 13.2(j). The Terms show an effective date of 10 Nov 2026, which the entry does not state.
- control_interfaces.yaml | Ubisoft policy quote | couldn't check | There is no Ubisoft policy quote in the file. The only Ubisoft mention is in the AutoHotkey entry's policy field (line 658), which points to "policy notes in the summary and in gaps (Ubisoft, Bungie)". Neither the summary nor the gaps section mentions Ubisoft or Bungie. That reference dangles. Not fetched: there is no quote to check.

## Totals

- game_envs.yaml: 6 picked, 6 confirmed, 0 wrong, 0 couldn't check
- npc_mods.yaml: 6 picked, 6 confirmed, 0 wrong, 0 couldn't check
- control_interfaces.yaml: 6 picked, 6 confirmed, 0 wrong, 0 couldn't check (plus policy-quote checks: 3 confirmed, 1 wrong (citation pointer), Ubisoft: no quote present, couldn't check)

Wrong lines:
- control_interfaces.yaml | vrchat-osc, policy quote citing "Terms section 13.2" for the automation ban: the clause is 13.2(j).
