# Jarvis: research and feature blueprint

Prepared for Marky / MarkyADHD, 24 September 2026.

Updated 25 September 2026 with personality, two-way calling, dual-PC control, Claude Code extensions and 20 additional proposed capabilities. The master prompt has been updated in place with these requirements.

## Recommendation

Build a personal Windows application around Claude's agent runtime, with an independent voice service, Windows automation bridge, durable task and memory store, creator tools and a private phone interface. Make common commands fast and deterministic. Use Claude for reasoning, research and unfamiliar workflows. Give Jarvis broad capabilities through verified tools and a general operator fallback, with visible execution and an immediate stop mechanism.

**User clarification incorporated:** Claude should provide search, research, coding, reasoning and other existing runtime capabilities. Do not build a parallel search engine, model orchestrator or duplicate tools by default. Detect what the selected Claude runtime exposes and extend only the missing capabilities. An unavailable built-in tool should produce a clear setup requirement, not a silent new paid dependency.

This is a build recommendation, not a claim that a finished product or every integration has been tested. The research below uses official documentation, original project repositories and vendor feature descriptions. Hardware performance, account eligibility, installed app versions and device compatibility still need checking on your PC. Vendor demonstrations and latency claims are not independent benchmarks.

No present-day assistant can reliably do absolutely anything. The useful target is an extensible assistant that can handle a large and growing range of tasks, recognise when it is stuck and show evidence of what it completed. It should never say it changed a setting, saved a clip or sent a message unless that action actually succeeded.

## 1. What existing assistants teach us

| Project or platform | Documented strengths | How I would use the idea for your Jarvis |
|---|---|---|
| Claude Agent SDK | Embeds the agent loop behind Claude Code, with tools, sessions, hooks and permission controls. [1] | Primary reasoning and task execution engine behind your own interface. |
| Claude Code CLI and Remote Control | Programmatic operation and remote access to a session running on your machine. [2][3] | Development engine and an optional phone route for native Claude Code work. |
| OpenClaw | A self-hosted gateway connecting messaging channels to agents; its security guidance explicitly describes trust boundaries. [5][6] | Borrow persistent jobs, channel adapters and a central gateway concept. Do not add it as another mandatory runtime without a concrete need. |
| Open Interpreter | A computer-oriented assistant with desktop interaction and local execution. [7] | Reference for visible computer operation and task-oriented interaction. |
| OpenVoiceOS | Modular voice assistant platform and skills ecosystem. [8] | Borrow replaceable speech components and explicit skill contracts. |
| Leon | Open-source personal assistant with speech and skill-oriented design. [9] | Reference for personal workflows and extensibility. |
| Home Assistant Assist | Configurable voice pipelines and local smart-home control. [10] | Optional device hub when the lighting setup grows. |
| Pipecat | Speech pipeline, turn detection and interruption handling. [11] | Preferred starting point for the Python voice service, subject to a Windows compatibility spike. |
| LiveKit Agents | Turn management and interruptions, including handling what was actually heard. [12] | Strong alternative if phone audio transport becomes the main engineering difficulty. |
| Letta and Mem0 | Persistent memory abstractions and memory management APIs. [17][18] | Learn from their separation of memories and context. Start with a simpler local store rather than making several memory services mandatory. |
| StreamLadder / ClipGPT | Vendor describes highlight discovery, vertical layouts, facecam framing, captions, transcript search and posting workflows. [25] | Feature benchmark for your own clipping studio, not a verified promise of equivalent quality or access to its private implementation. |

The best design for you combines these ideas. Installing every framework would add overlapping state, more processes and more failure points. There is no independent evidence here that one assistant is universally the best.

## 2. The Claude Code decision that must happen first

There are three different things to keep separate:

1. **Claude Code writes Jarvis.** You use it in the project folder to implement and maintain the application.
2. **Jarvis uses Claude's agent runtime.** The Agent SDK is the purpose-built embedded interface; the documented CLI interface is an alternative. [1][2]
3. **You control a native Claude Code session from your phone.** Remote Control keeps execution on the PC, while the phone supplies another interface. It does not automatically supply a custom Jarvis dashboard, wake word or speech system. [3]

The official documentation distinguishes ordinary native subscription usage from authentication for applications. Do not assume a Claude subscription is an unlimited backend allowance for a custom app. Use the documented authentication route appropriate to the selected integration, keep API billing visible and verify personal-use eligibility before relying on subscription-backed operation. Do not copy hidden OAuth credentials into Jarvis or invent a third-party Claude login. [4]

**Recommended default:** Agent SDK integration with supported authentication and a visible cost budget. Provide a clearly documented native CLI option only if current documentation supports the intended personal workflow. Support official Remote Control separately for development sessions.

Claude inference still depends on Anthropic or another supported cloud deployment. Local UI, local files and local execution do not make Claude an offline model. A local fallback can operate lights, open applications and run known routines without pretending to have Claude's full reasoning quality.

## 3. Recommended architecture

| Layer | Proposed implementation | Reason |
|---|---|---|
| Desktop UI | Electron, React and TypeScript | Strong desktop integration, tray behaviour and shared web UI components. Electron needs hardened renderer boundaries. [35] |
| Phone UI | Responsive web app / installable PWA | Shares conversation, jobs, approvals and clips with the PC. |
| Local backend | Node.js / TypeScript service, typed HTTP and WebSocket events | One authoritative place for sessions, tool permissions and jobs. |
| Claude agent | Agent SDK adapter | Keeps model and runtime integration replaceable. |
| Speech | Python service with Pipecat, local wake detection, replaceable STT and TTS | Low-latency audio must not be blocked by long agent tasks. |
| Windows bridge | Native Windows worker using UI Automation, pywinauto and narrowly scoped OS operations | More reliable than screenshot-only clicking where controls are exposed. [32][33] |
| Browser | Playwright with a dedicated user-authorised browser profile | Semantic selectors, waiting and evidence of browser actions. [34] |
| Memory and jobs | SQLite with FTS5, plus optional local vector index | Simple local operation, explicit retention and restart recovery. [19] |
| Creator rendering | FFmpeg and ffprobe worker, optional NVIDIA acceleration | Repeatable media processing outside the UI process. [26][27] |
| Devices | Direct local adapters initially; optional Home Assistant bridge | Avoid requiring another server just to control a light. |
| Remote connection | Tailscale Serve with app authentication and device revocation | Private HTTPS path rather than a publicly exposed PC controller. [36] |

Start with a modular application, not a distributed microservice platform. Python sidecars are justified for audio, media and Windows libraries, but Docker, Redis, Kubernetes and a separate database server are not baseline requirements.

### Two execution routes

**Fast route:** “Mute Jarvis”, “save replay”, “set the key light to 40%”, “open Discord”, “sleep”. Resolve these through validated local commands and known routines. A cloud model should not be necessary for every action.

**Reasoning route:** “Find today's videos”, “make five good clips from this recording”, “fix this project”, “create a Blender scene”. Claude plans, calls tools, checks results and updates the task. Reuse learned procedures only after they have been verified.

Both routes use the same execution policy and cancellation system. Fast must not mean unaccountable.

## 4. A catalogue of 100 worthwhile features

These are proposed requirements, not claims that an existing product supplies all of them. Foundation items should precede optional advanced work.

### Voice and personality

1. Local “Jarvis” wake phrase with adjustable sensitivity.
2. Push-to-talk from a keyboard key, Stream Deck and phone.
3. A roughly 60-second follow-up conversation window.
4. British-English recognition with a personal vocabulary for names and gaming terms.
5. Turn detection that tolerates pauses and unfinished sentences.
6. Interrupt speech by saying “Jarvis”.
7. Immediate “Jarvis stop”, plus a local emergency hotkey.
8. “Sleep” that stops active control and queued actions until an explicit wake.
9. Natural British voice, speed and verbosity controls, with voice preview.
10. “Sir” by default, confident British banter and funny natural swearing, with adjustable professional/clean modes and no repetitive canned phrases.

### Memory and personal knowledge

11. Conversation context shared between desktop and phone.
12. Editable personal preferences and naming rules.
13. Project memory separated by project.
14. Search across authorised documents and notes.
15. A visible “what do you remember?” memory viewer.
16. “Remember”, “correct that” and “forget that” commands.
17. Sources, dates and confidence for remembered facts.
18. Automatic expiry of transient memory after 14 days.
19. Persistent pinned memories only when explicitly selected.
20. A private mode that does not retain conversation content.

### PC and browser operation

21. Discover installed applications and custom aliases.
22. Focus an existing app instead of launching duplicates.
23. Read and operate accessible Windows controls.
24. Visual fallback for otherwise inaccessible interfaces.
25. Multi-monitor and mixed-DPI coordinate handling.
26. File search, organisation, rename and reversible moves.
27. Authorised clipboard reading, transformations and paste.
28. Browser research, form filling and downloads.
29. Troubleshoot apps from relevant logs and observed state.
30. Visible live action view with pause, takeover and task receipts.

### Productive work

31. Research answers with links and dates.
32. Documents, spreadsheets, presentations and PDFs through suitable tools.
33. Code editing, testing, Git diffs and reversible checkpoints.
34. Email and message drafting, with explicit sending controls.
35. Calendar, reminders, timers and recurring jobs.
36. A daily briefing based on selected sources.
37. Meeting or voice-note summaries when recording is authorised.
38. Task breakdown, prioritisation and progress tracking.
39. Reusable routines taught in ordinary language.
40. Overnight background jobs with completion notifications.

### Streaming production

41. OBS connection health and scene/source control.
42. Recording and replay-buffer management.
43. A stream preparation routine with preflight checks.
44. Audio routing presets for private or on-stream Jarvis speech.
45. Twitch chat and event awareness.
46. Stream markers and clip commands.
47. Approved title, category and channel-management changes.
48. Cooldown-controlled lighting reactions to authorised stream events.
49. Resource-aware gaming mode that pauses heavy analysis.
50. Post-stream report with markers, candidate clips and next actions.

### Clip creation and editing

51. “Clip that” local replay capture.
52. Manual timestamp bookmarks during a stream.
53. Whole-recording transcription with searchable timestamps.
54. Highlight suggestions based on context, events and audio cues.
55. Clip ranking with reasons and uncertainty.
56. Editable vertical facecam-plus-gameplay layouts.
57. Word-timed captions with corrections and reusable styles.
58. Crop, trim, zoom, blur, audio cleanup and optional silence trimming.
59. Batch exports with titles, descriptions, thumbnails and subtitle files.
60. A review queue with accept/reject feedback and publishing handoff.

### Lighting and hardware

61. Key Light power, brightness and colour temperature.
62. Nanoleaf power, brightness and supported effects.
63. Device discovery with a manual-IP fallback.
64. Combined “stream”, “editing”, “chill” and “rave” scenes.
65. Restore previous lighting after a temporary effect.
66. Music-responsive lighting from a selected loopback audio source.
67. Stream Deck buttons with visible status feedback.
68. Optional Home Assistant integration for wider smart-home devices.
69. Device disconnect recovery and clear unsupported-model reporting.
70. Hardware-specific extensions added through adapters rather than guesses.

### Remote assistant

71. Phone text chat and foreground push-to-talk.
72. Review and approve sensitive actions from the phone.
73. See live task progress and selected PC screenshots.
74. Review, play and download finished clips remotely.
75. Upload a phone photo or file to an authorised task.
76. Trigger routines while away from the PC.
77. Revoke lost devices and expire sessions.
78. Explicit offline, sleeping and locked-PC states.
79. Optional Wake-on-LAN only when the actual network supports it.
80. Remote stop commands with an acknowledgement from the PC.

### UI and experience

81. Original dark, cinematic command-centre visual design.
82. Readable chat with attached files and tool result cards.
83. A small voice orb reflecting real listening/thinking/speaking states.
84. Task timeline showing current action, evidence and blockers.
85. An approvals inbox describing the exact proposed change.
86. Memory, connections, routines and privacy settings.
87. A proper clip studio with timeline and crop preview.
88. Tray controls, global shortcut and opt-in startup at sign-in.
89. Keyboard accessibility, reduced motion and responsive phone layout.
90. Honest empty/error states instead of fake connected dashboards.

### Reliability and control

91. A durable job queue that survives restart.
92. Duplicate-action prevention after reconnects and retries.
93. Per-task and daily API spend limits.
94. Measured voice latency and interruption diagnostics.
95. Restore points or backups for applicable edits.
96. Redacted activity records and clear execution receipts.
97. Stream privacy that protects speech, screen views and notifications.
98. Explicit tool permissions and trusted input sources.
99. Acceptance tests based on your real previous failures.
100. A staged extension system with provenance and rollback.

## 5. Voice: what makes it feel like Jarvis

A convincing voice assistant needs more than fast text-to-speech. The pipeline has to recognise when you started, wait until you finished, stream a useful answer, stop when interrupted and prevent its own output from becoming a new command.

Pipecat documents separate turn-start and turn-end behaviour with voice activity and semantic turn detection. LiveKit offers another implementation with interruptions and heard-speech context handling. These are useful reference designs, but the cancellation of your own PC tools must still be implemented separately. [11][12]

| Component | Candidates | Recommendation |
|---|---|---|
| Wake detection | openWakeWord, or a licensed alternative if testing is poor | Try local openWakeWord using its Windows-supported inference path; test your pronunciation and ambient stream audio. [13] |
| Speech recognition | faster-whisper locally; a supported streaming STT API optionally | Benchmark local recognition first on your actual mic and GPU load. faster-whisper itself is not a complete conversational streaming system. [14] |
| Turn detection | Voice activity plus semantic endpointing | Separate thinking pauses from completed sentences. |
| Local speech | Kokoro or Piper | Compare naturalness, Windows dependencies, voice licences and resource usage. [15][16] |
| Cloud speech | ElevenLabs streaming voice | Optional quality profile with visible usage. Its advertised model latency excludes the whole STT/model/network/playback path. [20] |
| Audio transport | Local pipeline initially; WebRTC when phone speech is added | Keep one owner of each microphone and one authoritative speech queue. |

Use a licensed original British voice with a composed, helpful personality. An earlier model called `jgkawell/jarvis` is a preference to investigate, not a dependency to trust without establishing what it is, how it runs and whether the voice assets are appropriate.

Proposed engineering targets, not performance promises: a local emergency hotkey should mute output rapidly, ideally within 150 ms; a recognised spoken stop should cut local speech ideally within 300 ms of detection; a simple cached local action should normally be dispatched within roughly half a second; first meaningful speech on an ordinary cloud turn should aim for 1–2 seconds median on a healthy connection. Measure the complete latency and p95 tails. Do not satisfy the target by playing “one moment” while the real answer takes ten seconds.

## 6. PC control: broad access with reliable execution

Use application APIs first, then browser/Windows accessibility interfaces, and screenshot-based control when needed. Windows UI Automation exposes controls; pywinauto provides Windows automation libraries; Playwright locators provide semantic browser targets and built-in waiting. [32][33][34]

Whole-PC capability is different from running everything permanently as Administrator. Run the desktop controller in your interactive Windows session. Handle elevation explicitly. Lock screens, secure desktops, anti-cheat-protected games, unavailable accessibility trees and unusual custom interfaces can block automation. Never disable Windows protections to pretend the assistant has solved those limitations.

The most important execution rules are: observe the current state, choose the correct target, perform an action, verify the resulting state and return a receipt. Before clicking, check whether a window moved or focus changed. Stop after bounded unsuccessful retries. Allow you to take over without fighting the mouse.

For coding and creative production, direct tools often outperform mouse automation. Blender has a Python API; Unreal exposes editor scripting through Python. These provide routes to scene generation and asset manipulation, but do not guarantee a production-quality character from one image or arbitrary control of a packaged game. [38][39]

## 7. Streaming and lights

OBS has built-in WebSocket support in current releases, with an official protocol for controlling it. Implement against the installed version and authenticate the connection. Save replay buffers and recordings through OBS instead of trying to scrape the preview window. [21][22]

Use Twitch OAuth and EventSub for authorised channel data and events. Event handling must tolerate reconnection and duplicate delivery. Chat is external content, not an administrative command channel. If you later enable viewer-controlled lights, expose narrowly defined commands with limits; do not give chat the PC controller. [23]

Twitch's current API reference includes VOD clip creation and clip-download endpoints. The VOD creation API uses an end offset rather than a start offset, so a timestamp mistake can select the wrong moment. Build from the current reference and test with your own channel. The general clips guide and detailed reference differ on some timing guidance, so avoid hard-coding assumptions from the overview. [24]

For lighting, Key Light supports local control through the Home Assistant integration. That integration distinguishes brightness/colour temperature from RGB features on other Elgato products. Nanoleaf's panel API and Home Assistant integration do not imply every Essentials bulb uses the same route. Discover the precise product and choose its supported local API, Matter/Thread or HomeKit path. [28][29][30]

Use Stream Deck's official SDK for physical controls. A dedicated stop key, push-to-talk key, clip key and stream-mode indicator would be more valuable initially than dozens of decorative buttons. [31]

Your music can reach a reactive-lighting analyser through a selected loopback source even when you are listening through headphones. This is a proposed PC audio feature, not a promise that a particular light supports arbitrary real-time effects. Identify what each device can actually display.

## 8. Making clips like StreamLadder

Build this in two stages: **reliable manual capture and editing**, then **automatic highlight discovery**. A good editor is useful even when AI ranking is imperfect.

The recommended local pipeline is:

1. Save an OBS replay or import an authorised recording.
2. Inspect tracks, duration, timestamps and frame rate with ffprobe.
3. Create a low-resolution preview and transcribe the selected audio.
4. Build candidate moments from manual markers, transcript context, reactions and optional chat/event spikes.
5. Review setup and payoff around each moment; avoid chopping off the joke.
6. Score candidates for editorial usefulness, with reasons. Do not label the score a predicted probability of going viral.
7. Apply a saved gameplay/facecam layout, with manual crop controls.
8. Correct captions, add branding and adjust timing in the preview.
9. Render an MP4 and optional subtitle files using repeatable FFmpeg jobs.
10. Review before publishing, or apply an explicitly authorised standing publishing policy.

FFmpeg supplies crop, scale, composition, subtitles and loudness-processing tools; NVIDIA documents hardware acceleration paths. A configured FFmpeg build still needs the required codecs and filters, and concurrent OBS encoding can create resource contention. [26][27]

Do not send a full six-hour video to a language model by default. Use local transcription and signals to narrow candidates, then send only the relevant excerpts or sampled frames if cloud analysis is enabled. Analyse chat only when collected through an authorised route; do not promise unavailable historic chat replay.

Publishing to YouTube, TikTok and Instagram is a separate integration project. Account type, permissions, quotas and app approval may affect it. Export plus a manual publishing handoff must always work even when an upload API is unavailable. StreamLadder's integrations are not evidence that a new personal app receives the same platform access.

## 9. Memory that is useful and controllable

Separate current conversation, temporary episodes, persistent preferences, project knowledge, and verified procedures. Put records in a local database and index only the folders you authorise. Full-PC file capability must not silently become perpetual indexing of every private file.

Use the earlier preference of `E:\Jarvis\data` when the drive exists. Keep transient conversation and inferred facts for 14 days by default. Preserve only intentionally pinned preferences, selected project records and explicit “remember this” facts beyond that period. If E: is unavailable, show degraded status rather than silently scattering the memory store across drives.

Every memory should have provenance, creation time, expiry and sensitivity. Updating a fact should supersede the old one. “Forget this” must remove it from active retrieval, derived summaries and vector indexes, while clearly explaining any remaining backup or provider-retention limitation. Deleting a local memory cannot guarantee deleting data already processed by a cloud provider.

Letta and Mem0 are useful references for persistent memory design; SQLite full-text search is a practical initial local component. These are alternatives to evaluate, not three compulsory systems to install together. [17][18][19]

## 10. Phone access and original UI

For your own UI, make the phone a client of the same backend. It should see the same conversations, running jobs and clip queue, and use the same stop system. Tailscale Serve can expose a service privately within a tailnet. Add application sessions and device revocation; private network membership alone is not the entire access policy. [36]

Browser microphone capture needs a secure context and permission. Treat foreground push-to-talk as the dependable mobile baseline and test the actual iPhone/browser. Do not promise a web page will remain an always-listening voice assistant after the phone locks or the OS suspends it. [37]

The PC must be awake, online and running Jarvis for local jobs to execute. Queue future work when disconnected, but distinguish queued work from completed work. Wake-on-LAN needs compatible hardware, firmware and an appropriate network path, potentially another always-on device.

Visual direction: charcoal, warm white, restrained cyan, crisp typography and an original animated central motif. Use real task cards, a readable transcript, a clip editor and a small amount of purposeful motion. Avoid movie assets, copied HUD layouts, actor voice imitation and franchise branding. This is a creative direction to make the design original, not a legal clearance opinion.

## 11. Privacy and cost are operating features

When streaming, Jarvis should be able to route speech privately, suppress private notifications and avoid saying your location, addresses, secrets or unrelated personal details. Redact before cloud upload, logging, speech and remote viewing where applicable. Hiding something in the UI after it was already sent to a provider does not prevent disclosure.

Use an execution policy implemented in code, not just a sentence asking the model to behave. Arbitrary shell access under the same Windows user weakens any claimed file boundary: the implementation must either gate broad execution, isolate it with real OS controls or honestly state the remaining exposure. MCP and Playwright are connection mechanisms, not security boundaries. [40][41]

Keep model access, remote control and optional providers separately priced in the UI. Exact monthly cost cannot be predicted without model choice, context sizes, voice minutes and media usage. Show usage, estimates where available, daily caps, per-task caps and cancellation on budget exhaustion. Cap parallel reasoning jobs and avoid expensive analysis during a stream.

One material change from the old Jarvis: Google says Custom Search JSON API is closed to new customers, with existing customers required to transition by 1 January 2027. There is no reason to revive that dependency here: use Claude's available search/research tools. Verify their availability under the selected runtime, authentication and permission configuration. [42]

## 12. Build order and release gates

| Stage | Working deliverable | Evidence required |
|---|---|---|
| 0. Discovery | Hardware/app inventory, architecture decisions, dependency versions and cost setup | Actual local checks, with secrets redacted. |
| 1. Core | Desktop chat, Claude adapter, task records, stop control, local storage | A real request, restart recovery and no fake success states. |
| 2. Voice | Push-to-talk, streaming reply, wake phrase, interruption and sleep | Your mic, your accent and tests for the old speech bugs. |
| 3. PC operator | App discovery/focus, browser and Windows control | Multi-step task verified on Windows; no duplicate launches. |
| 4. Stream producer | OBS, Twitch, Key Light, Nanoleaf and basic routines | Real connected devices or an explicit blocked status. |
| 5. Clip studio | Replay capture, editable vertical export and captions | A playable exported file with correct framing and audio. |
| 6. Phone | Private access, chat, jobs, review and remote stop | A task initiated on the phone and completed on the PC. |
| 7. Advanced | Highlight ranking, wider integrations and creative workflows | Feature-specific acceptance tests and resource measurements. |

The full scope is a substantial application, not a single evening's script. The accompanying build prompt instructs Claude Code to implement usable slices, keep a completion ledger and continue across sessions. It should not claim the whole system is finished because a polished dashboard opens.

## 13. Personality update

Your requested “don't give a fuck” mentality now means an original, confident, cheeky British assistant who can swear, tease lightly and give blunt feedback. It should feel natural rather than like every answer was forced through a comedy filter.

The prompt separates style from actual execution. Jarvis can say “OBS isn't connected. That rather fucks up the scene change” while still accurately reporting the failure and checking the connection. It cannot claim success just to sound confident. Professional drafts and serious conversations get an appropriate tone. Banter, profanity, teasing and proactive chatter are separate controls; you can keep swearing on your stream if you want.

## 14. Yes, you can call Jarvis and he can call you

**Real phone calls are technically feasible.** Twilio documents making/receiving calls and a bidirectional audio connection to an application. LiveKit documents SIP telephony as an alternative. These are connection layers; our design keeps Claude as the reasoning engine. [43][44][46]

| Route | Experience | Recommended role |
|---|---|---|
| In-app voice over your private connection | Open Jarvis on the phone and speak to the same assistant | Build first using the existing audio system. No telephone number is needed, although existing model/voice/network costs can remain. |
| A real telephone number | Save Jarvis as a contact and ring him; he can call your enrolled mobile | Optional Twilio adapter, or LiveKit telephony if LiveKit is already the chosen audio layer. |
| A separate voice-agent platform | Another platform can manage calls and audio | Not the default: evaluate only if it materially reduces work without replacing or duplicating the agreed Claude core. |

OpenClaw also documents a voice-call plugin, providing a concrete reference for the kind of assistant calling you have seen. It is an OpenClaw integration, not a drop-in Claude Code plugin. [47]

My recommended uses are calls you ask for: “call me when the renders finish”, “remind me by phone in ten minutes”, or a specific enabled alert for a sustained stream failure. Normal updates should remain notifications unless you choose calls. Add quiet hours, a call-duration cap, one-attempt defaults and a clear hang-up control.

There is an architectural detail worth getting right: the telephone provider must reach the communications endpoint. Twilio requires secure WebSocket connectivity and signature validation. A private Tailscale URL alone will not automatically provide that. A narrow public relay can receive call audio while the PC connects outbound; the desktop-control service remains private. [44]

A normal phone number is not strong proof of who is calling. The proposed design requires enrolment and additional authentication for private information or PC control, especially consequential actions. If the main PC is asleep, callers hear an unavailable message or use an explicitly enabled voice-message workflow. It cannot carry out local work while its host is off.

Phone rental, call minutes, speech processing, Claude usage and any relay hosting can each contribute to cost. UK number availability, verification requirements and exact rates must be checked during setup before purchasing anything. This research did not buy a number, activate a service or test a live call.

Telephone interruptions must clear audio already buffered at the provider. Twilio documents audio format requirements plus clear/mark messages; stopping only the local speaker would be insufficient. [45]

## 15. Dual-PC setup: a central assistant with a second-PC companion

This is now a core requirement, not merely an optional idea. The proposed companion is a small app installed on the second PC. It receives authorised tasks, runs local tools and sends results back. Claude sessions, personal memory and schedules remain on the main PC.

| On the main PC | On the companion PC | On your phone |
|---|---|---|
| Claude connection, memory, planning, scheduling and task history | App discovery/control, selected-screen capture, local OBS adapter and optional media worker | One interface to both PCs, with target selection and the same conversations |
| Central permissions and budgets | Local permission enforcement, control indicator and emergency stop | Approvals, task progress, clip review and call controls |

OpenClaw's node documentation illustrates the wider gateway-plus-companion pattern; it does not prove our custom Windows implementation exists. Tailscale supplies configurable network access controls, while application pairing and permission enforcement still need to be built. [48][49]

The most useful examples for you:

- “Open OBS on the streaming PC.”
- “Save that replay on the streaming PC and edit it on the main PC.”
- “Put this finished clip on the other machine.”
- “Show me the streaming PC's screen on my phone.”
- “Prepare both PCs for tonight.”

The app will map roles explicitly rather than assume the main PC is the gaming PC. Each command carries a target machine. If a machine disconnects, old mouse clicks must not replay when it reconnects. A local timeout and stop control release input even when the main controller is unreachable. Existing OBS streams continue unless an authorised command actually stops them.

The companion does not need its own Claude model instance simply to run local tools. Additional AI processing would have its normal costs. Moving media work to it is optional and should depend on available hardware, transfer time and current game/OBS load.

## 16. Your four plugin names, checked

These are research findings, not installed extensions or security-audit results. Similar names are common; exact repository identity matters.

| Name | What I could establish | Recommendation |
|---|---|---|
| Ponytail | The `DietrichGebert/ponytail` project provides a Claude-compatible simplification skill/plugin. [50] | Try during development with a restrained setting. Preserve readability and required behaviour. Treat the author's benchmark claims as project-specific. |
| Omnicloud | I could not establish which Claude Code extension you mean. A similarly named `OmniNode-ai/omniclaude` exists and describes an ONEX integration. [51] | Keep this unresolved until you supply the link/screenshot. Do not install a guess. |
| Graphify | Examined `Graphify-Labs/graphify`, a project knowledge-graph tool. Its documented code-only path is local; broader semantic extraction can involve a model. [52] | Optional, scoped to authorised project code initially. |
| Agent skills | This is also the name of a general open format. Anthropic has an official skills repository, while many separate collections exist. [53][54] | Start with selected relevant official skills. The exact collection you saw remains unidentified. |

The plugin section explicitly distinguishes tools used to build Jarvis from tools loaded into the running assistant. A development plugin does not automatically appear in the embedded Claude runtime or on the other PC.

Additional candidates worth evaluating:

| Extension | Potential value for Jarvis | Priority |
|---|---|---|
| Anthropic frontend-design | UI implementation guidance | High during UI work. [55] |
| Anthropic code-review | Development review at suitable checkpoints | Useful when its repository workflow fits. [56] |
| Anthropic security-guidance | Additional development guidance | Useful supplement, not protection by itself. [57] |
| Microsoft Playwright MCP | Browser operations and UI verification | Only if direct Playwright is not already sufficient. [41] |
| Upstash Context7 | Version-specific library documentation | Optional development aid; Claude remains the general research system. [58] |
| obra Superpowers | Structured debugging, testing and development workflow | Optional: examine mandatory hooks and process overhead before adding. [59] |

Install a small set matched to the current milestone. Graphify does not replace personal memory. Ponytail does not make code automatically secure. Skills do not grant missing account access. OpenClaw plugins do not become Claude Code plugins because both products use AI. The prompt asks Claude Code to verify actual installation and loading, with disable/uninstall paths. [60]

## 17. Twenty more proposed capabilities

The original 100-feature catalogue remains above. This extra pass adds these priorities, with implementations and limits in the master prompt:

101. Cross-device task and conversation handoff.
102. Event-based escalation from normal notifications to authorised calls.
103. OBS incident diagnosis with observed evidence and bounded recovery routines.
104. A cross-PC recording and output location map.
105. A searchable creator asset library.
106. Per-game and per-scene clip layouts.
107. Clip privacy review and manually correctable redaction.
108. A phone voice-note inbox tied to projects.
109. “Talk me through this screen” assistance without automatic takeover.
110. A hotkey for selected text or selected screen regions.
111. Optional focus sessions and gentle task check-ins.
112. A central undo centre for genuinely reversible actions.
113. Deliberate workflow recording, then reviewable routine generation.
114. Cross-PC dry runs showing intended actions and costs.
115. Recording/export health checks for common media failures.
116. A conversation-to-task draft inbox.
117. A resource-aware overnight queue across both PCs.
118. Unified connector and device diagnostics.
119. A personal briefing of jobs, stream prep and clip review.
120. Controlled discovery of missing skills and integrations.

These are proposed product behaviours informed by the research, not claims that installing one plugin supplies them. The revised prompt contains 45 acceptance scenarios, including telephone authentication, provider audio cancellation, target-machine routing, companion disconnects and personality changes.

## Sources

Sources were consulted during this research. Documentation can change; pin and record the versions used during implementation. Platform descriptions above are deliberately distinguished from the proposed Jarvis features.

1. Anthropic, [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview).
2. Anthropic, [Run Claude Code programmatically](https://code.claude.com/docs/en/headless).
3. Anthropic, [Remote Control](https://code.claude.com/docs/en/remote-control).
4. Anthropic, [Legal and compliance: authentication and credential use](https://code.claude.com/docs/en/legal-and-compliance).
5. OpenClaw, [Documentation](https://docs.openclaw.ai/).
6. OpenClaw, [Gateway security](https://docs.openclaw.ai/gateway/security).
7. Open Interpreter, [Desktop documentation](https://www.openinterpreter.com/docs/desktop).
8. OpenVoiceOS, [Project repository](https://github.com/OpenVoiceOS/OpenVoiceOS/blob/main/README.md).
9. Leon, [Introduction](https://docs.getleon.ai/).
10. Home Assistant, [Assist pipelines](https://developers.home-assistant.io/docs/voice/pipelines/).
11. Pipecat, [Speech input and turn detection](https://docs.pipecat.ai/pipecat/learn/speech-input).
12. LiveKit, [Turns overview](https://docs.livekit.io/agents/logic/turns/).
13. openWakeWord, [Project repository](https://github.com/dscripka/openWakeWord).
14. SYSTRAN, [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
15. Hexgrad, [Kokoro-82M model card](https://huggingface.co/hexgrad/Kokoro-82M).
16. Open Home Foundation, [Piper](https://github.com/OHF-Voice/piper1-gpl).
17. Letta, [Memory blocks](https://www.letta.com/blog/memory-blocks/).
18. Mem0, [Self-hosting guide](https://mem0.ai/blog/self-host-mem0-docker).
19. SQLite, [FTS5](https://sqlite.org/fts5.html).
20. ElevenLabs, [Models](https://elevenlabs.io/docs/overview/models).
21. OBS, [Remote Control Guide](https://obsproject.com/kb/remote-control-guide).
22. OBS Project, [WebSocket protocol](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md).
23. Twitch, [Handling EventSub WebSocket events](https://dev.twitch.tv/docs/eventsub/handling-websocket-events/).
24. Twitch, [API reference](https://dev.twitch.tv/docs/api/reference), especially Create Clip, Create Clip From VOD and Get Clips Download.
25. StreamLadder, [ClipGPT feature description](https://www.streamladder.com/clipgpt).
26. FFmpeg, [Filter documentation](https://ffmpeg.org/ffmpeg-filters.html).
27. NVIDIA, [Using FFmpeg with NVIDIA GPU hardware acceleration](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/ffmpeg-with-nvidia-gpu/index.html).
28. Home Assistant, [Elgato Light integration](https://www.home-assistant.io/integrations/elgato/).
29. Nanoleaf, [API quick start](https://support.nanoleaf.me/hc/en-us/articles/41105798500628-API-Quick-Start-Guide).
30. Home Assistant, [Nanoleaf integration](https://www.home-assistant.io/integrations/nanoleaf/).
31. Elgato, [Stream Deck SDK](https://docs.elgato.com/streamdeck/sdk/introduction/getting-started/).
32. Microsoft, [UI Automation fundamentals](https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiautocore-overview).
33. pywinauto, [Project repository](https://github.com/pywinauto/pywinauto).
34. Playwright, [Locators](https://playwright.dev/docs/locators).
35. Electron, [Security guidance](https://www.electronjs.org/docs/latest/tutorial/security).
36. Tailscale, [Serve](https://tailscale.com/docs/features/tailscale-serve).
37. MDN, [getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).
38. Blender, [Python API overview](https://docs.blender.org/api/current/info_overview.html).
39. Epic Games, [Scripting the Unreal Editor using Python](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python).
40. Model Context Protocol, [Security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices).
41. Microsoft, [Playwright MCP](https://github.com/microsoft/playwright-mcp).
42. Google, [Custom Search JSON API overview](https://developers.google.com/custom-search/v1/overview).
43. Twilio, [Call resource and inbound/outbound call model](https://www.twilio.com/docs/voice/api/call-resource).
44. Twilio, [Media Streams overview and connection security](https://www.twilio.com/docs/voice/media-streams).
45. Twilio, [WebSocket audio, clear and mark messages](https://www.twilio.com/docs/voice/media-streams/websocket-messages).
46. LiveKit, [Telephony introduction](https://docs.livekit.io/telephony/).
47. OpenClaw, [Voice-call plugin](https://docs.openclaw.ai/plugins/voice-call).
48. OpenClaw, [Companion nodes](https://docs.openclaw.ai/nodes).
49. Tailscale, [Access control policies](https://tailscale.com/docs/features/access-control/acls).
50. Dietrich Gebert, [Ponytail](https://github.com/DietrichGebert/ponytail).
51. OmniNode, [OmniClaude, a possible name match only](https://github.com/OmniNode-ai/omniclaude).
52. Graphify Labs, [Graphify](https://github.com/Graphify-Labs/graphify).
53. Agent Skills, [Format overview](https://agentskills.io/home).
54. Anthropic, [Official skills repository](https://github.com/anthropics/skills).
55. Anthropic, [Frontend-design plugin](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/frontend-design/README.md).
56. Anthropic, [Code-review plugin](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/code-review/README.md).
57. Anthropic, [Security-guidance plugin](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/security-guidance/README.md).
58. Upstash, [Context7 Claude plugin](https://github.com/upstash/context7/blob/master/plugins/claude/context7/README.md).
59. obra, [Superpowers](https://github.com/obra/superpowers).
60. Anthropic, [Install/manage plugins](https://code.claude.com/docs/en/discover-plugins) and [skill integration](https://code.claude.com/docs/en/skills).
