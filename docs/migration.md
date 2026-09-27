# Migration map (Python → Electron rebuild)

Baseline: v2.20 (commit b320ff1). Old launch path: `Launch Jarvis.bat` → `venv\Scripts\pythonw.exe jarvis_app_v2.py`, which imports every module below.
Rollback: the Python app is untouched on this branch; `git checkout main` or keep using `Launch Jarvis.bat`.
Nothing is retired yet. No Python file is deleted until its replacement is verified on the Windows PC.

New launch path (dev): `npm install` once, then `npm start`.

## Data
| Old store | New owner | Migration | State |
|---|---|---|---|
| `E:\JarvisMemory\jarvis_long_memory_v2.jsonl` (fallback `C:\AI-Agent\JarvisMemory`) | `src/main/store.js` → `%APPDATA%\jarvis\data\memories.jsonl` | Read-only copy on every start, idempotent, original fields/timestamps kept, `source` + `importedAt` added | Implemented, unit-tested; unverified against real file |
| `jarvis_profile_v2.json` | store | not yet | Planned |
| Obsidian vault `C:\Users\babym\Jarvis Memory` | stays in place; Claude reads it | none needed | Planned (expose path to Claude) |

## Modules
| Old module | Purpose | New owner | State |
|---|---|---|---|
| `jarvis_aliases_v1.py` |  | | Not ported |
| `jarvis_app.py` |  | | Not ported |
| `jarvis_app_v2.py` |  | | Not ported |
| `jarvis_attachments_v1.py` | Jarvis Attachment Intelligence V1 | | Not ported |
| `jarvis_brain_v2.py` |  | | Not ported |
| `jarvis_claude_brain_v2.py` | Persistent, tool-enabled Claude brain (Claude Agent SDK, via backtalk's | `src/main/claude.js` (warm stream-json session, persona, cancel) | Partial |
| `jarvis_claude_code_v1.py` |  | | Not ported |
| `jarvis_clipper_v1.py` | Jarvis Clipper V1 | | Not ported |
| `jarvis_code_watch_v1.py` | Jarvis Code-Change Announcement V1 | | Not ported |
| `jarvis_context_compressor_v1.py` | Jarvis Context Compressor V1 | | Not ported |
| `jarvis_control_cli.py` | Command-line entry point onto Jarvis's own existing fast-path command | | Not ported |
| `jarvis_conversation_v4.py` |  | | Not ported |
| `jarvis_creative_v2.py` | Jarvis Creative Writer V2 | | Not ported |
| `jarvis_debug_boot.py` |  | | Not ported |
| `jarvis_desktop_v2.py` |  | | Not ported |
| `jarvis_dictionary_v1.py` | Jarvis Dictionary V1 -- "define X" / "what does the word X mean". | | Not ported |
| `jarvis_discord_v1.py` | Jarvis Discord Control V1 | | Not ported |
| `jarvis_face_window.py` | Persistent JARVIS face: a standalone app-like window (Edge app mode, | | Not ported |
| `jarvis_goal_mode_v32.py` | Jarvis PC Control V3.2 - Goal Mode | | Not ported |
| `jarvis_guardian_v1.py` | Guardian V2: DISABLED at the user's explicit request (2026-09-08). | | Not ported |
| `jarvis_intelligence_core_v3.py` | Jarvis Intelligence Core V3 | | Not ported |
| `jarvis_interrupt_v1.py` |  | Stop button / Esc / tray Stop (text only; voice stop is milestone 2) | Partial |
| `jarvis_iss_v1.py` | Jarvis Space V1 -- "where is the ISS" / "how many people are in space". | | Not ported |
| `jarvis_learning.py` |  | | Not ported |
| `jarvis_lights_v1.py` | Jarvis Lights V1 | | Not ported |
| `jarvis_link_intelligence_v1.py` |  | | Not ported |
| `jarvis_maintainer_cli.py` |  | | Not ported |
| `jarvis_maintainer_v1.py` | Jarvis Autonomous Maintainer V2; preserves the V1 import/API names. | | Not ported |
| `jarvis_maintenance_runner_v2.py` | Fixed, bounded, offline smoke/regression runner. No application imports. | | Not ported |
| `jarvis_maps_v1.py` | Jarvis Maps V1 -- "directions to X" / "show me X on the map". | | Not ported |
| `jarvis_media_v1.py` | Jarvis Media Core V1 | | Not ported |
| `jarvis_memory.py` |  | | Not ported |
| `jarvis_memory_v2.py` |  | `src/main/store.js` (long-memory import only) | Partial |
| `jarvis_mini_bar.py` | jarvis_mini_bar.py -- a small, click-through, animated bar that hovers | | Not ported |
| `jarvis_nanoleaf_revoke_token.py` |  | | Not ported |
| `jarvis_nanoleaf_setup_v1.py` |  | | Not ported |
| `jarvis_network_health_v1.py` | Jarvis Network Health V1 | | Not ported |
| `jarvis_notes_v1.py` | Jarvis Quick Notes V1 | | Not ported |
| `jarvis_onboarding_v1.py` | Jarvis Onboarding V1 | | Not ported |
| `jarvis_operator_v1.py` | Jarvis PC Operator V1.1 JSON Hotfix | | Not ported |
| `jarvis_operator_v2.py` | Jarvis Operator V2.1 Hybrid Direct Control | | Not ported |
| `jarvis_pc_control_v3.py` | Jarvis PC Control V3.1 - Fast Screen Awareness + UI Automation | | Not ported |
| `jarvis_personality_v2.py` |  | `src/main/claude.js` PERSONA | Partial |
| `jarvis_process_dedup_v1.py` | Jarvis Process Dedup V1 | Electron single-instance lock | Partial |
| `jarvis_provider_router_v1.py` | Jarvis Provider Router V1 | | Not ported |
| `jarvis_recall_v1.py` | Jarvis Recall V1 | | Not ported |
| `jarvis_reminders_v1.py` | Jarvis Reminders V1 | | Not ported |
| `jarvis_remote_chat.py` | jarvis_remote_chat.py -- talk to Jarvis remotely over Tailscale. | | Not ported |
| `jarvis_response_v2.py` | Jarvis Response Parser V2 | | Not ported |
| `jarvis_search_intelligence_v3.py` | Jarvis Search Intelligence V3 | | Not ported |
| `jarvis_search_intelligence_v4.py` |  | | Not ported |
| `jarvis_settings_v1.py` | Jarvis Settings & Setup V1 | | Not ported |
| `jarvis_shutdown_systems_v1.py` | Jarvis Shutdown Systems V1 | | Not ported |
| `jarvis_skill_mode.py` |  | | Not ported |
| `jarvis_spotify_auth_setup.py` | One-time Spotify Control V2 setup. | | Not ported |
| `jarvis_spotify_v2.py` | Jarvis Spotify Control V2.1 Hotfix | | Not ported |
| `jarvis_steam_v1.py` | Jarvis Steam V1 | | Not ported |
| `jarvis_system_media_helper.py` | Jarvis System Media Helper | | Not ported |
| `jarvis_system_media_v1.py` | Jarvis System Media V1 | | Not ported |
| `jarvis_system_stats_v1.py` | Jarvis System Stats V1 | | Not ported |
| `jarvis_tailscale_v1.py` | Jarvis Tailscale Control V1 | | Not ported |
| `jarvis_tasks_v1.py` | Jarvis Voice Tasks V1 | | Not ported |
| `jarvis_thumbnail_v1.py` | Jarvis Thumbnail V1 | | Not ported |
| `jarvis_tool_intelligence_v1.py` |  | | Not ported |
| `jarvis_twitch_v1.py` | Jarvis Twitch Control V1 | | Not ported |
| `jarvis_uber_v1.py` | Jarvis Uber V1 | | Not ported |
| `jarvis_ui_hud_v4.py` | Native Tk HUD for Jarvis. Drawing and widget updates stay on the UI thread. | `src/renderer/` (basic chat, no HUD visuals yet) | Partial |
| `jarvis_ui_v2.py` | Jarvis UI V2 | | Not ported |
| `jarvis_ui_v3.py` | Jarvis UI V3 | | Not ported |
| `jarvis_update_check_v1.py` | Jarvis Update Check V1 | | Not ported |
| `jarvis_web.py` |  | | Not ported |
| `jarvis_world_time_v1.py` | World clock: "what time is it in <place>" style questions. | | Not ported |
| `jarvisclipper_app.py` | JarvisClipper -- launcher. | | Not ported |
| `jarviscode_app.py` | JarvisCode -- launcher. | | Not ported |
| `jarvistrader_app.py` | JarvisTrader (BETA) -- launcher. | | Not ported |

## Ported to v3 (2026-09-26)
Now in `src/tools/pc.js` (Claude's single allowed tool) unless noted. The Python modules are untouched.
- jarvis_world_time_v1.py -> `time [city]`
- jarvis_notes_v1.py -> `note add/list/clear`
- jarvis_steam_v1.py -> `game list/launch`
- jarvis_system_stats_v1.py -> HUD telemetry panels + `info`
- jarvis_system_media_v1.py / helper -> `media` + Now Playing (`nowplaying.ps1`)
- jarvis_lights_v1.py (Elgato part) -> `light`
- jarvis_pc_control_v3.py (basic) -> `open`, `volume`, `lock`, `screen`
- search -> Claude's own WebSearch/WebFetch
- weather / briefing / dictionary / ISS / maps -> new, public APIs with no keys
- jarvis_ui_hud_v4.py -> full remake in src/renderer/hud.*
Still Python-only: Spotify API playback, Discord, Twitch, Nanoleaf/Hue, clipper, thumbnails, trader, Tailscale/remote chat.
- jarvisclipper (clip cutting) -> Clip Studio (src/main/clips.js + src/renderer/clip.js) + `pc.js clip`. yt-dlp downloading isn't ported yet.
- yt-dlp downloading -> Clip Studio 'Fetch' (clips.download), standalone yt-dlp via winget
- jarvis_thumbnail_v1.py -> src/main/thumbs.js (frame or Pollinations background + title). SDXL/Gemini backends not ported.
