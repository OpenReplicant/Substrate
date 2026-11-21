# Game catalogs (research, 2026-11-21)

Four catalogs of ways an agent can take part in a game or virtual world, gathered by research agents from pages
they read. They are raw sources for the `catalog` skill, not yet written into the store (the Knowledge Kernel).

| File | The agent as | Entries |
| --- | --- | --- |
| `game_envs.yaml` | a player: environments and benchmarks an agent plays, solo, co-op or multiplayer | 40 |
| `npc_mods.yaml` | the voice and mind of NPCs: mods that hand NPC dialogue or actions to a model | 33 |
| `control_interfaces.yaml` | a helper on a person's controller, or its own avatar through a platform's interface (OSC, MCP, bots) | 31 |
| `gm_interfaces.yaml` | a game master: a god's-eye view of a server, and the admin or modding hooks to change it | 34 |

Each fact names the page it came from; facts seen only in a search result are marked `(snippet)`, and what was not
found is `unknown`. Each file opens with a summary, its gaps and leads not yet read. `spotcheck.md` is a check of
six random entries per file (the first three) against their sources: 18 of 18 held; the fixes it found are made.

## Where they overlap: a world where the game master, the players and the NPCs can all be agents

A platform appears below when the catalogs found a way in for each role. "Control" is how much of the world an
agent can change.

| Platform | Game master | Players | NPCs | Control | Notes |
| --- | --- | --- | --- | --- | --- |
| Minecraft (Java) | GameMasterMC (Apache-2.0, Paper plugin, any OpenAI-compatible model), minecraft-rcon-mcp (MIT) | Mineflayer, Mindcraft (MIT), MineDojo, MineRL | Smart Villagers AI (Apache-2.0), AI Companion Fabric (LGPLv3) | commands, plugins, datapacks: nearly everything | the most existing pieces; the game is not open source, a local server is free to run |
| Luanti (Minetest) | Lua mods on the server | listed in `game_envs.yaml` | none with a model found | Lua mods: everything | engine and game fully open; fewer AI pieces exist |
| OpenSimulator | region modules | avatars as bots through LibreMetaverse (BSD-3-Clause) | the same bots | region scripts: everything | fully open and multi-user; old technology |
| Resonite | the host, through ResoniteLink and its MCP bridges | presence as a user is not documented | in-world objects driven over ResoniteLink | what the host grants | a social world; its terms on bots were not read |
| Garry's Mod | Lua, GTerm (MIT, MCP) | not found | three NPC mods | Lua: nearly everything | |
| Factorio | RCON and Lua | the Factorio Learning Environment | none | Lua: everything | no NPCs to speak of |
| Evennia (a MUD engine) | Python, all of it | any client that types | an LLM chat-bot contrib | everything | text only: the cheapest place to try the loop |
| Godot, Unity, Unreal | editor MCP servers | whatever you build | NPC kits (Player2 and others) | everything, once built | you build the world first |

Not on this list: games whose terms forbid automation (VRChat's terms ban "automated means"; Ubisoft and Bungie
ban AI-driven controllers), recorded in `control_interfaces.yaml`.
