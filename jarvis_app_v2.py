import jarvis_settings_v1 as settings_v1
settings_v1.load_environment()

r"""
Jarvis Brain V2 + Memory V2 + Personality V2 + Desktop V2 compatibility launcher.

This does not replace your main jarvis_app.py.
It imports your working Jarvis app, upgrades routing/memory/personality/desktop actions, then launches it.

Run:
    cd C:\AI-Agent
    .\venv\Scripts\python.exe .\jarvis_app_v2.py
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import requests
from pathlib import Path

import jarvis_app as app
import jarvis_brain_v2 as brain
import jarvis_memory_v2 as memory
import jarvis_personality_v2 as personality
import jarvis_desktop_v2 as desktop
import jarvis_ui_v2 as ui
import jarvis_ui_v3 as ui3
import jarvis_operator_v1 as operator_v1
import jarvis_operator_v2 as operator_v2
import jarvis_pc_control_v3 as pc_control_v3
import jarvis_response_v2 as response_v2
import jarvis_creative_v2 as creative_v2
import jarvis_attachments_v1 as attachments_v1
import jarvis_goal_mode_v32 as goal_v32
import jarvis_media_v1 as media_v1
import jarvis_spotify_v2 as spotify_v2
import jarvis_keylight_v1 as keylight_v1
import jarvis_nanoleaf_v1 as nanoleaf_v1
import jarvis_hue_v1 as hue_v1
import jarvis_govee_v1 as govee_v1
import jarvis_process_dedup_v1 as process_dedup_v1
import jarvis_update_check_v1 as update_check_v1
import jarvis_twitch_v1 as twitch_v1
import jarvis_clipper_v1 as clipper_v1
import jarvis_thumbnail_v1 as thumbnail_v1
import jarvis_uber_v1 as uber_v1
import jarvis_steam_v1 as steam_v1
import jarvis_provider_router_v1 as provider_router
import jarvis_onboarding_v1 as onboarding_v1
import jarvis_discord_v1 as discord_v1
import jarvis_tailscale_v1 as tailscale_v1
import jarvis_room_lights_v1 as room_lights_v1
import jarvis_shutdown_systems_v1 as shutdown_systems_v1
import jarvis_interrupt_v1 as interrupt_v1
import jarvis_aliases_v1 as aliases_v1
import jarvis_maintainer_v1 as maintainer_v1
import jarvis_intelligence_core_v3 as intelligence_v3
import jarvis_search_intelligence_v3 as search_v3
import jarvis_search_intelligence_v4 as search_v4
import jarvis_link_intelligence_v1 as link_v1
import jarvis_tool_intelligence_v1 as tool_v1
import jarvis_conversation_v4 as conversation_v4
import jarvis_claude_code_v1 as claude_v1
import jarvis_claude_brain_v2 as claude_brain_v2
import jarvis_world_time_v1 as world_time_v1


_original_log = getattr(app, "log", None)

_DEBUG_LOG_PATH = Path(r"C:\AI-Agent\jarvis_live_debug.log")
_DEBUG_LOG_MAX_BYTES = 5 * 1024 * 1024  # rotate before this becomes a
# multi-day, ever-growing file -- it had no cap at all before, and
# opening/writing/closing the file from scratch on every single log
# line (this fires constantly -- every heard command, every reply,
# every background event) was needless per-call open/close syscall
# overhead on top of that. One handle held open for the process
# lifetime, flushed after each write so a crash still leaves the log
# readable, fixes both at once.
_debug_log_lock = threading.Lock()
_debug_log_handle = None


def _open_debug_log():
    global _debug_log_handle
    if _debug_log_handle is not None:
        return _debug_log_handle
    try:
        if _DEBUG_LOG_PATH.exists() and _DEBUG_LOG_PATH.stat().st_size > _DEBUG_LOG_MAX_BYTES:
            rotated = _DEBUG_LOG_PATH.with_suffix(".log.old")
            try:
                rotated.unlink()
            except FileNotFoundError:
                pass
            _DEBUG_LOG_PATH.rename(rotated)
    except Exception:
        pass
    try:
        _debug_log_handle = open(_DEBUG_LOG_PATH, "a", encoding="utf-8")
    except Exception:
        _debug_log_handle = None
    return _debug_log_handle


def _log_to_file_v2(message):
    """Temporary diagnostic mirror: the HUD is hidden now (by design), so
    its on-screen conversation/log view isn't visible to check anymore.
    Mirror every log line to a plain file so live issues (wake word not
    heard, a false live-interrupt trigger, an exception) can be read back
    without un-hiding the window.

    This same code runs inside TWO separate OS processes -- the main app
    and jarvis_remote_chat.py both import this module and both call
    install_v2(), which installs this as app.log -- and both write into
    the SAME file path. Each process holds its own independent file
    handle, so when one process rotates (renames the current file out of
    the way), the other's handle would otherwise keep silently writing
    into the renamed file, and a later rotation by the first process
    could delete it while the second still has it open. Comparing the
    handle's own file identity (st_ino) against what the path currently
    points to on every write catches exactly that: whichever process's
    handle got orphaned by the other one's rotation reopens against the
    real current file instead of writing into a file that's about to
    vanish.
    """
    global _debug_log_handle
    try:
        with _debug_log_lock:
            f = _open_debug_log()
            if f is not None:
                try:
                    on_disk = _DEBUG_LOG_PATH.stat()
                    stale = os.fstat(f.fileno()).st_ino != on_disk.st_ino
                    oversized = on_disk.st_size > _DEBUG_LOG_MAX_BYTES
                except Exception:
                    stale = oversized = False
                if stale or oversized:
                    f.close()
                    _debug_log_handle = None
                    f = _open_debug_log()
                if f is not None:
                    f.write(f"{time.strftime('%H:%M:%S')} {message}\n")
                    f.flush()
    except Exception:
        pass

    if _original_log:
        return _original_log(message)


_original_JarvisApp = getattr(app, "JarvisApp", None)

if _original_JarvisApp:
    class _HiddenJarvisApp_v2(_original_JarvisApp):
        """The old Tkinter HUD is still the actual engine -- wake-word
        listening, memory, and every Spotify/lights/media/PC-control fast
        path live in it, not in the new ai-visualizer face, which is a pure
        display with no logic of its own. So it still has to run. It never
        has to be VISIBLE though: the new face is meant to be the only
        thing on screen, so hide this window the moment it's built instead
        of showing both. Everything __init__ starts (listening, live view,
        prewarm threads) already runs before this fires.
        """
        def __init__(self, root):
            super().__init__(root)
            try:
                self.hide_window()
            except Exception:
                try:
                    root.withdraw()
                except Exception:
                    pass


_original_quick_handle_command = getattr(app, "quick_handle_command", None)
_original_should_use_web_search = getattr(app, "should_use_web_search", None)
_original_clean_web_query = getattr(app, "clean_web_query", None)
_original_answer_with_web_context = getattr(app, "answer_with_web_context", None)
_original_web_fast = getattr(app, "web_fast", None)
_original_run_agent_task = getattr(app, "run_agent_task", None)
_original_speak = getattr(app, "speak", None)
_original_ask_ai = getattr(app, "ask_ai", None)
_original_ask_ai_chat = getattr(app, "ask_ai_chat", None)
_original_speak_worker = getattr(app, "speak_worker", None)

SPEECH_STOP_REQUESTED = threading.Event()


def safe_name():
    try:
        profile = memory.load_profile()
        identity = profile.get("identity", {})
        saved = str(identity.get("preferred_spoken_name", "")).strip()
        if saved:
            return saved
    except Exception:
        pass

    try:
        return brain.get_spoken_name()
    except Exception:
        return "Sir"


def refresh_spoken_name():
    name = safe_name()

    try:
        app.USER_SPOKEN_NAME = name
    except Exception:
        pass

    return name


def app_normalise(text):
    if hasattr(app, "normalize_transcript"):
        return app.normalize_transcript(text)
    return brain.normalise(text)


def stop_speaking_now():
    SPEECH_STOP_REQUESTED.set()

    try:
        pg = getattr(app, "pygame", None)
        if pg is None:
            import pygame as pg

        try:
            pg.mixer.music.stop()
        except Exception:
            pass

        try:
            pg.mixer.stop()
        except Exception:
            pass
    except Exception:
        pass

    for attr in [
        "SPEECH_STOP_REQUESTED",
        "STOP_SPEAKING",
        "STOP_REQUESTED",
        "INTERRUPT_REQUESTED",
        "AUTOPILOT_STOP_REQUESTED",
        "autopilot_stop_requested",
    ]:
        try:
            current = getattr(app, attr, None)

            if hasattr(current, "set"):
                current.set()
            else:
                setattr(app, attr, True)
        except Exception:
            pass

    try:
        app.log("Stop requested.")
    except Exception:
        pass


def app_speak(text):
    if _original_speak:
        return _original_speak(text)
    print(text)


def sync_name_to_memory(name):
    try:
        memory.set_profile_value("identity", "preferred_spoken_name", name)
    except Exception:
        pass


def _record_v3_error(context, error):
    try:
        maintainer_v1.record_error(context, error=error)
    except Exception:
        pass



def _conversation_model_resolver_v4(raw_text, context_text):
    payload = {
        "model": app.OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Rewrite a conversational follow-up into one self-contained "
                    "Jarvis request. Use working context only when the new message "
                    "clearly refers to it. Preserve exact names, URLs, numbers, "
                    "dates, platforms and quoted text. If this is a new topic, "
                    "return it unchanged. Do not answer the request. Return only "
                    "the rewritten request."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"WORKING CONTEXT:\n{context_text}\n\n"
                    f"NEW MESSAGE:\n{raw_text}"
                ),
            },
        ],
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.02,
            "num_predict": 120,
            "num_ctx": 4096,
        },
    }

    # A local call generating 120 tokens has no business being allowed
    # 80s -- if Ollama ever actually stalled, Jarvis would sit silently
    # "thinking" for a minute and a half before this even times out.
    # 20s matches the equivalent resolver in jarvis_intelligence_core_v3.py.
    response = requests.post(
        "http://localhost:11434/api/chat",
        json=payload,
        timeout=20,
    )

    response.raise_for_status()

    return str(
        response.json()
        .get("message", {})
        .get("content", "")
        or ""
    ).strip()


def _resolve_conversation_v4(command):
    cleaned = intelligence_v3.clean_input(command)

    try:
        resolved = conversation_v4.resolve(
            cleaned,
            model_resolver=_conversation_model_resolver_v4,
        )
    except Exception as e:
        _record_v3_error("conversation_v4.resolve", e)
        return cleaned

    if resolved != cleaned:
        try:
            app.log(
                f"Conversation V4 resolved: {cleaned} -> {resolved}"
            )
        except Exception:
            pass

    return resolved


def prepare_command_v3(command):
    try:
        conversation_resolved = _resolve_conversation_v4(command)

        prepared = intelligence_v3.prepare_request(
            conversation_resolved,
            model=getattr(app, "OLLAMA_MODEL", "qwen2.5vl:7b"),
            persist=True,
        )
        resolved = str(prepared.get("resolved_text") or prepared.get("clean_text") or command)
        c = app_normalise(resolved)

        if intelligence_v3.normalise(prepared.get("clean_text", "")) != intelligence_v3.normalise(resolved):
            try:
                app.log(f"Intelligence V3 context resolved: {prepared.get('clean_text', '')} -> {resolved}")
            except Exception:
                pass

        return prepared, c
    except Exception as e:
        _record_v3_error("intelligence_v3.prepare_request", e)
        cleaned = intelligence_v3.clean_input(command)
        return {
            "raw_text": str(command or ""),
            "clean_text": cleaned,
            "resolved_text": cleaned,
            "was_followup": False,
            "topic": "",
            "intent_family": intelligence_v3.intent_family(cleaned),
        }, app_normalise(cleaned)


def finish_plan_v3(plan, goal, name, route="chat"):
    polished = personality.polish_plan(plan, goal, name)

    try:
        intelligence_v3.note_result(
            goal,
            polished.get("reply", ""),
            route=route,
        )
    except Exception as e:
        _record_v3_error("intelligence_v3.note_result", e)

    try:
        conversation_v4.note_reply(
            polished.get("reply", ""),
            tool=route,
            source_url=str(
                polished.get("source_url", "")
                or polished.get("url", "")
                or ""
            ),
            entity=conversation_v4.guess_entity(goal),
            action=route,
            action_target=goal,
        )
    except Exception as e:
        _record_v3_error("conversation_v4.note_reply", e)

    return polished


def _tool_web_lookup_v1(command, name):
    query = clean_web_query_v2(command)
    research = search_v4.research_with_precision(
        query,
        research_func=lambda q, max_results=8: app.web_research(q, max_results=max_results),
        max_results=getattr(app, "WEB_MAX_RESULTS", 8),
        max_attempts=5,
        use_ddgs_fallback=True,
    )
    web_data = research.get("web_data", {}) or {}
    diagnostics = research.get("diagnostics", {}) or {}
    precision = search_v4.direct_precision_plan(query, web_data, spoken_name=name)

    source_url = ""
    candidates = diagnostics.get("precision_candidates", []) or []
    if candidates:
        source_url = str(candidates[0].get("url", "") or "")
    if not source_url:
        for collection in (web_data.get("results", []) or [], web_data.get("pages", []) or []):
            for item in collection:
                if not isinstance(item, dict):
                    continue
                source_url = str(item.get("url") or item.get("link") or item.get("source_url") or "").strip()
                if source_url:
                    break
            if source_url:
                break

    if precision:
        reply = str(precision.get("reply", "") or "").strip()
        return {"status": "succeeded", "reply": reply, "data": {"reply": reply, "answer": reply, "source_url": source_url}}

    if not diagnostics.get("public_relevance_ok"):
        return {"status": "failed", "reply": "I couldn't find relevant public evidence for that.", "data": {"source_url": ""}}

    memory_parts = []
    try:
        x = memory.memory_context_for_prompt(query, limit=10)
        if x:
            memory_parts.append(str(x))
    except Exception:
        pass
    try:
        x = brain.get_profile_context()
        if x:
            memory_parts.append(str(x))
    except Exception:
        pass

    try:
        web_context = app.format_web_context(web_data)
    except Exception:
        web_context = ""

    plan = grounded_web_answer_v3(
        query,
        web_context,
        memory_context="\n\n".join(memory_parts),
        search_diagnostics=diagnostics,
    )
    reply = str(plan.get("reply", "") or "").strip()
    return {"status": "succeeded" if reply else "unknown", "reply": reply, "data": {"reply": reply, "answer": reply, "source_url": source_url}}


def _tool_open_url_v1(url, name):
    import webbrowser
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"status": "failed", "reply": "I didn't have a valid URL to open."}
    try:
        opened = bool(webbrowser.open(url))
    except Exception as e:
        _record_v3_error("tool_v1.open_url", e)
        return {"status": "failed", "reply": f"I couldn't open the page: {e}"}
    return {"status": "succeeded" if opened else "attempted", "reply": f"I opened the source page, {name}.", "data": {"url": url, "source_url": url}}


def _tool_registry_v1(name):
    return {
        "web": lambda command: _tool_web_lookup_v1(command, name),
        "open_url": lambda url: _tool_open_url_v1(url, name),
        "link": lambda command: link_v1.link_command_fast(command, name, app, search_module=search_v4),
        "spotify": lambda command: spotify_v2.spotify_command_fast(command, name, app),
        "media": lambda command: media_v1.media_command_fast(command, name, app),
        "lights": lambda command: (room_lights_v1.room_lights_command_fast(command, name, app) or nanoleaf_v1.nanoleaf_command_fast(command, name, app) or keylight_v1.keylight_command_fast(command, name, app) or hue_v1.hue_command_fast(command, name, app) or govee_v1.govee_command_fast(command, name, app)),
        "pc": lambda command: (goal_v32.goal_command_fast(command, name, app) or pc_control_v3.operator_command_fast(command, name, app) or operator_v2.operator_command_fast(command, name, app) or operator_v1.operator_command_fast(command, name, app)),
        "attachment": lambda command: attachments_v1.attachment_command_fast(command, name, app),
        "memory": lambda command: memory.memory_command_fast(command, name),
    }


def quick_handle_command_v2(command):
    name = refresh_spoken_name()
    prepared, c = prepare_command_v3(command)
    clean_raw = str(prepared.get("clean_text") or command)
    family = str(prepared.get("intent_family") or intelligence_v3.intent_family(c))

    if c in {
        "conversation status",
        "conversation memory",
        "working memory status",
        "what are we talking about",
    }:
        return {
            "mode": "chat",
            "reply": f"{conversation_v4.summary()} {name}.",
            "steps": [],
        }

    if c in {
        "clear conversation",
        "clear conversation context",
        "clear working memory",
        "forget this conversation",
    }:
        conversation_v4.clear("user_requested")
        return {
            "mode": "chat",
            "reply": f"I cleared the current conversation context, {name}.",
            "steps": [],
        }

    claude_result = claude_v1.command_fast(clean_raw, name)
    if not claude_result and c != clean_raw:
        claude_result = claude_v1.command_fast(c, name)
    if claude_result:
        return finish_plan_v3(claude_result, c, name, "claude")

    # Checked early and ahead of generic conversation routing on purpose:
    # a bare "yes" confirming a pending update announcement needs to land
    # here, not get swallowed as small talk. Returns None immediately for
    # anything that isn't an update check/confirmation, so it costs
    # nothing on the common path.
    update_result = update_check_v1.update_command_fast(c, name, app)
    if update_result:
        return finish_plan_v3(update_result, c, name, "update_check")

    twitch_result = twitch_v1.twitch_command_fast(c, name, app)
    if twitch_result:
        return finish_plan_v3(twitch_result, c, name, "twitch")

    clipper_result = clipper_v1.clipper_command_fast(c, name, app)
    if clipper_result:
        return finish_plan_v3(clipper_result, c, name, "clipper")

    thumbnail_result = thumbnail_v1.thumbnail_command_fast(c, name, app)
    if thumbnail_result:
        return finish_plan_v3(thumbnail_result, c, name, "thumbnail")

    uber_result = uber_v1.uber_command_fast(c, name, app)
    if uber_result:
        return finish_plan_v3(uber_result, c, name, "uber")

    steam_result = steam_v1.steam_command_fast(c, name, app)
    if steam_result:
        return finish_plan_v3(steam_result, c, name, "steam")

    if c in {"open jarviscode", "open jarvis code", "launch jarviscode", "launch jarvis code", "start jarviscode", "start jarvis code"}:
        try:
            subprocess.Popen(
                [sys.executable, "jarviscode_app.py"],
                cwd=r"C:\AI-Agent",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return finish_plan_v3(
                {"mode": "chat", "reply": f"Opening JarvisCode, {name}.", "steps": []},
                c, name, "jarviscode_launch",
            )
        except Exception as e:
            return finish_plan_v3(
                {"mode": "chat", "reply": f"I couldn't open JarvisCode, {name}: {e}", "steps": []},
                c, name, "jarviscode_launch",
            )

    brain_result = provider_router.brain_command_fast(c, name, app)
    if brain_result:
        return finish_plan_v3(brain_result, c, name, "provider_router")

    discord_result = discord_v1.discord_command_fast(c, name, app)
    if discord_result:
        return finish_plan_v3(discord_result, c, name, "discord")

    tailscale_result = tailscale_v1.tailscale_command_fast(c, name, app)
    if tailscale_result:
        return finish_plan_v3(tailscale_result, c, name, "tailscale")

    # Core/system commands stay deterministic and fast.
    maintainer_result = maintainer_v1.maintainer_command_fast(c, name, app)
    if maintainer_result:
        return finish_plan_v3(maintainer_result, c, name, "maintainer")

    settings_result = settings_v1.settings_command_fast(c, name, app)
    if settings_result:
        return finish_plan_v3(settings_result, c, name, "settings")

    shutdown_result = shutdown_systems_v1.shutdown_command_fast(c, name, app)
    if shutdown_result:
        return finish_plan_v3(shutdown_result, c, name, "shutdown")

    # Stop is always authoritative.
    if interrupt_v1.is_stop_command(clean_raw) or interrupt_v1.is_stop_command(c):
        interrupt_v1.request_stop(app, reason="voice_stop")
        try:
            app.stop_all_current_work()
        except Exception:
            pass
        return {"mode": "chat", "reply": "", "steps": []}

    alias_result = aliases_v1.alias_command_fast(clean_raw, name)
    if alias_result:
        return finish_plan_v3(alias_result, c, name, "alias")

    c = aliases_v1.apply_aliases(c)
    family = intelligence_v3.intent_family(c)

    # WORLD CLOCK PRECHECK
    # Checked ahead of link/tool intelligence and web-search routing on
    # purpose: "what time is it in India" was getting misread by the tool
    # planner as a PC-control goal (it tried to "open a clock app" with
    # india as a window-focus target) on some phrasings, and by the web-
    # search heuristic as a fresh-info lookup on others -- both wrong,
    # and the web path returned scraped junk instead of a real answer
    # (confirmed live for India). Returns None (falls through completely
    # unchanged) for any place this fixed table doesn't recognise.
    world_time_result = world_time_v1.world_time_fast(c, spoken_name=name)
    if world_time_result:
        return finish_plan_v3(world_time_result, c, name, "world_time")

    # LINK INTELLIGENCE V1 PRECHECK
    # Direct/profile navigation beats generic browser/search routing.
    link_result = link_v1.link_command_fast(
        clean_raw,
        name,
        app,
        search_module=search_v4,
    )
    if link_result:
        return finish_plan_v3(link_result, c, name, "link")


    # TOOL INTELLIGENCE V1 PRECHECK
    # Direct one-step commands remain on their normal fast path. Compound goals
    # use only the restricted registry above.
    if tool_v1.should_plan(c):
        try:
            tool_plan = tool_v1.run_goal(
                c,
                handlers=_tool_registry_v1(name),
                spoken_name=name,
                model_call=(
                    claude_v1.planner_model_call
                    if claude_v1.enabled()
                    else None
                ),
            )
        except Exception as e:
            _record_v3_error("tool_intelligence_v1.run_goal", e)
            tool_plan = None

        if tool_plan:
            try:
                app.log(
                    tool_v1.diagnostics(
                        tool_plan.get("_tool_plan", {}),
                        tool_plan.get("_tool_execution", {}),
                    )
                )
            except Exception:
                pass

            try:
                execution = tool_plan.get(
                    "_tool_execution",
                    {},
                )

                for outcome in (
                    execution.get("outcomes", [])
                    or []
                ):
                    conversation_v4.note_tool_result(
                        str(outcome.get("tool", "") or ""),
                        {
                            "reply": outcome.get("reply", ""),
                            "status": outcome.get("status", ""),
                            "data": outcome.get("data", {}),
                        },
                        command=str(
                            outcome.get("purpose", "")
                            or ""
                        ),
                    )
            except Exception as e:
                _record_v3_error("conversation_v4.tool_result", e)

            return finish_plan_v3(
                tool_plan,
                c,
                name,
                "tool_intelligence",
            )

    # Tool families only get first refusal when the central intent layer says
    # the user is actually controlling/querying that tool. This prevents a
    # branded word inside a normal question from hijacking conversation.
    if family == "lights":
        room_lights_result = room_lights_v1.room_lights_command_fast(c, name, app)
        if room_lights_result:
            return finish_plan_v3(room_lights_result, c, name, "lights")

        nanoleaf_result = nanoleaf_v1.nanoleaf_command_fast(c, name, app)
        if nanoleaf_result:
            return finish_plan_v3(nanoleaf_result, c, name, "nanoleaf")

        keylight_result = keylight_v1.keylight_command_fast(c, name, app)
        if keylight_result:
            return finish_plan_v3(keylight_result, c, name, "keylight")

        hue_result = hue_v1.hue_command_fast(c, name, app)
        if hue_result:
            return finish_plan_v3(hue_result, c, name, "hue")

        govee_result = govee_v1.govee_command_fast(c, name, app)
        if govee_result:
            return finish_plan_v3(govee_result, c, name, "govee")

    if family == "spotify":
        spotify_result = spotify_v2.spotify_command_fast(c, name, app)
        if spotify_result:
            return finish_plan_v3(spotify_result, c, name, "spotify")

    if family == "media":
        media_result = media_v1.media_command_fast(c, name, app)
        if media_result:
            return finish_plan_v3(media_result, c, name, "media")

    if family == "attachment":
        attachment_result = attachments_v1.attachment_command_fast(c, name, app)
        if attachment_result:
            return finish_plan_v3(attachment_result, c, name, "attachment")

    if family == "creative":
        creative_result = creative_v2.creative_command_fast(c, name, app)
        if creative_result:
            return finish_plan_v3(creative_result, c, name, "creative")

    if family == "pc":
        goal_result = goal_v32.goal_command_fast(c, name, app)
        if goal_result:
            return finish_plan_v3(goal_result, c, name, "goal")

        pc_control_result = pc_control_v3.operator_command_fast(c, name, app)
        if pc_control_result:
            return finish_plan_v3(pc_control_result, c, name, "pc")

        operator_v2_precheck = operator_v2.operator_command_fast(c, name, app)
        if operator_v2_precheck:
            return finish_plan_v3(operator_v2_precheck, c, name, "operator")

    if desktop.is_stop_command(c):
        stop_speaking_now()
        return {"mode": "action", "reply": "", "steps": []}

    # Explicit profile/personality/memory commands stay deterministic.
    name_result = brain.name_command_fast(c)
    if name_result:
        new_name = refresh_spoken_name()
        sync_name_to_memory(new_name)
        return finish_plan_v3(name_result, c, new_name, "profile")

    personality_result = personality.personality_command_fast(c, name)
    if personality_result:
        return finish_plan_v3(personality_result, c, name, "personality")

    memory_result = memory.memory_command_fast(c, name)
    if memory_result:
        return finish_plan_v3(memory_result, c, name, "memory")

    # V3 owns date/time interpretation. It only fires for true clock/calendar
    # questions; "what date does GTA 6 release" can never land here.
    date_time_result = intelligence_v3.local_datetime_plan(c, name)
    if date_time_result:
        return finish_plan_v3(date_time_result, c, name, "datetime")

    app_result = desktop.open_app_plan(c, name)
    if app_result and family != "question":
        return finish_plan_v3(app_result, c, name, "desktop")

    close_app_result = desktop.close_app_plan(c, name)
    if close_app_result and family != "question":
        return finish_plan_v3(close_app_result, c, name, "desktop")

    # Current/fresh facts are researched BEFORE legacy quick answers. This is
    # what makes release dates, prices, versions, schedules and current roles
    # behave like a modern assistant rather than stale local model knowledge.
    if should_use_web_search_v2(c):
        web_result = web_fast_v2(c)
        if web_result:
            return finish_plan_v3(web_result, c, name, "web")

    # PC/operator fallback remains available for commands that the lightweight
    # intent hint did not confidently classify.
    if family != "question":
        operator_v2_result = operator_v2.operator_command_fast(c, name, app)
        if operator_v2_result:
            return finish_plan_v3(operator_v2_result, c, name, "operator")

        operator_result = operator_v1.operator_command_fast(c, name, app)
        if operator_result:
            return finish_plan_v3(operator_result, c, name, "operator")

    # Legacy fast answers come last so they cannot override V3 current-fact
    # routing or conversational context resolution.
    if _original_quick_handle_command:
        result = _original_quick_handle_command(c)
        if result:
            return finish_plan_v3(result, c, name, "legacy_fast")

    return None

def force_web_intent(command):
    c = app_normalise(command)

    freshness_phrases = [
        "latest",
        "latest news",
        "news on",
        "news about",
        "breaking news",
        "current news",
        "recent news",
        "current information",
        "current info",
        "recent information",
        "recent updates",
        "latest updates",
        "latest update",
        "what happened today",
        "what happened this week",
        "today",
        "this week",
        "right now",
        "currently",
    ]

    explicit_web_phrases = [
        "search the internet",
        "search online",
        "look it up",
        "look this up",
        "look up",
        "check online",
        "check the internet",
        "find online",
        "research this",
        "research ",
        "browse the web",
        "web search",
    ]

    if any(phrase in c for phrase in freshness_phrases):
        return True

    if any(phrase in c for phrase in explicit_web_phrases):
        return True

    return False


def should_use_web_search_v2(command):
    try:
        cleaned = intelligence_v3.clean_input(command)
        family = intelligence_v3.intent_family(cleaned)

        if intelligence_v3.is_local_datetime_request(cleaned):
            return False

        # Existing tool actions must never be turned into web searches simply
        # because their text contains a product/service name.
        if family == "lights":
            return False
        if family in {"spotify", "media", "attachment", "creative", "pc", "memory"}:
            return False

        if intelligence_v3.needs_fresh_web(cleaned):
            return True

        if force_web_intent(cleaned):
            return True

        return brain.should_use_web_search(cleaned)
    except Exception as e:
        _record_v3_error("intelligence_v3.should_use_web_search", e)
        if _original_should_use_web_search:
            return _original_should_use_web_search(command)
        return False

def clean_web_query_v2(command):
    try:
        return brain.clean_web_query(command)
    except Exception:
        if _original_clean_web_query:
            return _original_clean_web_query(command)
        return command


def get_system_prompt():
    if hasattr(app, "system_prompt"):
        try:
            return app.system_prompt()
        except Exception:
            pass

    return getattr(app, "SYSTEM_PROMPT", "You are Jarvis.")


def answer_with_web_context_v2(goal, web_context):
    name = refresh_spoken_name()
    memory_context = memory.memory_context_for_prompt(goal, limit=8)

    messages = [
        {"role": "system", "content": brain.web_answer_prompt(name)},
        {"role": "system", "content": personality.style_prompt(name, goal)},
        {"role": "system", "content": web_context},
        {"role": "system", "content": memory_context},
        {"role": "user", "content": goal},
    ]

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": app.OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "format": "json",
            "keep_alive": "30m",
            "options": {
                "temperature": 0.15,
                "num_predict": 300,
                "num_ctx": 4096
            }
        },
        timeout=160
    )

    response.raise_for_status()
    content = response.json()["message"]["content"]

    try:
        plan = json.loads(content)
    except json.JSONDecodeError:
        plan = {
            "mode": "chat",
            "reply": f"I searched, but the model gave me a messy answer, {name}.",
            "steps": []
        }

    return personality.polish_plan(plan, goal, name)



def grounded_web_answer_v3(goal, web_context, memory_context="", search_diagnostics=None):
    name = refresh_spoken_name()
    search_diagnostics = search_diagnostics or {}
    entity = str(search_diagnostics.get("entity", "") or "").strip()
    public_ok = bool(search_diagnostics.get("public_relevance_ok"))
    memory_ok = bool(memory_context and search_v3.context_mentions_entity(memory_context, entity))

    # Prefer the warm, tool-having brain first: it has real WebSearch
    # access and, per CLAUDE.md, already prefers it over this module's
    # own scraping pipeline -- which has produced real garbage-snippet
    # answers before (the "$60 Bitcoin price" incident, and the
    # unprompted bitcoin/markyadhd repetition bugs that traced back to
    # bad pre-fetched context). The web_context below is handed over as
    # a starting point, not the only source of truth: the warm brain can
    # verify or replace it with a real WebSearch call if it looks thin,
    # off-topic, or wrong, rather than answering from bad research
    # verbatim the way the tool-less fallback below has to.
    try:
        warm_prompt = (
            f"Answer this question the user actually asked: \"{goal}\"\n\n"
            "Research already gathered by Jarvis's own search pipeline is "
            "below, as a head start, not a mandate -- if it looks thin, "
            "off-topic, or wrong, use your own WebSearch tool directly "
            "instead of trusting it. Never answer about a different topic "
            "than what was actually asked, even if the research below "
            "drifted onto something else.\n\n"
            f"RESEARCH GATHERED SO FAR:\n{web_context or '[none]'}\n\n"
            "RELEVANT MEMORY (private -- never present as a publicly "
            f"confirmed fact):\n{memory_context or '[none]'}\n\n"
            "Reply with just the spoken answer -- no markdown, no preamble."
        )
        warm_answer = provider_router.ask_active_brain(warm_prompt, spoken_name=name, timeout=45.0)
        if warm_answer.get("ok"):
            warm_reply = str(warm_answer.get("result", "") or "").strip()
            if warm_reply:
                return {"mode": "chat", "reply": warm_reply, "steps": []}
    except Exception as e:
        _record_v3_error("provider_router.ask_active_brain (grounded)", e)

    if claude_v1.enabled():
        try:
            claude_answer = claude_v1.answer_grounded(
                goal,
                web_context,
                memory_context=memory_context,
                entity=entity,
                public_ok=public_ok,
                memory_ok=memory_ok,
                spoken_name=name,
            )
            if claude_answer.get("ok"):
                claude_reply = str(claude_answer.get("result", "") or "").strip()
                if claude_reply:
                    return {"mode": "chat", "reply": claude_reply, "steps": []}
        except Exception as e:
            _record_v3_error("claude_v1.answer_grounded", e)

    system_prompt = (
        "You are Jarvis answering from research that has already been collected. "
        "PUBLIC WEB RESEARCH and PRIVATE JARVIS MEMORY are different evidence classes. "
        "Never present private memory as though it was publicly verified on the web. "
        "Use only PUBLIC WEB RESEARCH for claims that you describe as publicly confirmed. "
        "You may use PRIVATE JARVIS MEMORY to identify or contextualise a person/entity known to the user. "
        "If the public research is weak or empty, say that clearly instead of summarising irrelevant pages. "
        "For exact people, brands and handles, do not drift to similarly named or unrelated entities. "
        "Answer the user's actual question first. Be concise and natural. "
        "For latest/news requests, lead with the newest important development. "
        "Distinguish confirmed facts from rumours/speculation. Remove duplicate information. "
        "Return JSON only with keys reply and confidence."
    )

    evidence_status = (
        f"PRIMARY ENTITY: {entity or 'not detected'}\n"
        f"PUBLIC RELEVANCE PASSED: {public_ok}\n"
        f"PRIVATE MEMORY MATCHED ENTITY: {memory_ok}\n"
    )

    payload = {
        "model": app.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"QUESTION:\n{goal}\n\n"
                    f"{evidence_status}\n"
                    f"PRIVATE JARVIS MEMORY / PROFILE:\n{memory_context or '[none]'}\n\n"
                    f"PUBLIC WEB RESEARCH:\n{web_context or '[no relevant public web evidence survived relevance filtering]'}"
                )
            },
        ],
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {
            "temperature": 0.08,
            "num_predict": 750,
            "num_ctx": 8192,
        },
    }

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        content = str(response.json().get("message", {}).get("content", "") or "").strip()

        reply = intelligence_v3.extract_best_reply(content)

        bad = {
            "i'm not sure on that one yet, sir.",
            "im not sure on that one yet, sir.",
            "i'm not sure on that one yet.",
            "im not sure on that one yet.",
        }

        if reply and reply.lower().strip() not in bad:
            return {"mode": "chat", "reply": reply, "steps": []}

    except Exception as e:
        _record_v3_error("grounded_web_answer_v3.json", e)
        try:
            app.log(f"Grounded web JSON summary failed: {e}")
        except Exception:
            pass

    fallback_payload = {
        "model": app.OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer from the supplied evidence only. Keep public web evidence separate "
                    "from private Jarvis memory. Never imply private memory was publicly verified. "
                    "Do not summarise irrelevant sources. If no relevant public evidence survived, "
                    "say so briefly and use private memory only if it clearly matches the entity. "
                    "Do not output JSON."
                )
            },
            {
                "role": "user",
                "content": (
                    f"QUESTION:\n{goal}\n\n"
                    f"{evidence_status}\n"
                    f"PRIVATE JARVIS MEMORY / PROFILE:\n{memory_context or '[none]'}\n\n"
                    f"PUBLIC WEB RESEARCH:\n{web_context or '[none]'}"
                )
            },
        ],
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.1,
            "num_predict": 750,
            "num_ctx": 8192,
        },
    }

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json=fallback_payload,
            timeout=180,
        )
        response.raise_for_status()
        reply = str(response.json().get("message", {}).get("content", "") or "").strip()
        if reply:
            return {"mode": "chat", "reply": reply, "steps": []}
    except Exception as e:
        _record_v3_error("grounded_web_answer_v3.prose", e)

    if entity and memory_ok:
        return {
            "mode": "chat",
            "reply": (
                f"I know who {entity} refers to from my memory, {name}, "
                "but I couldn't find reliable public results that actually matched the name."
            ),
            "steps": [],
        }

    if entity:
        return {
            "mode": "chat",
            "reply": (
                f"I couldn't find reliable public information that actually matched "
                f"'{entity}', {name}. I discarded the unrelated results instead of guessing."
            ),
            "steps": [],
        }

    return {
        "mode": "chat",
        "reply": f"I found search results, {name}, but none were relevant enough to answer reliably.",
        "steps": [],
    }


def web_fast_v2(command):
    raw = intelligence_v3.clean_input(command)
    c = app_normalise(raw)
    name = refresh_spoken_name()

    if not should_use_web_search_v2(raw):
        return None

    if not getattr(app, "WEB_AVAILABLE", False):
        return {
            "mode": "chat",
            "reply": f"Internet mode is not loaded correctly, {name}.",
            "steps": []
        }

    query = clean_web_query_v2(raw)

    if not query:
        return {
            "mode": "chat",
            "reply": f"What should I search for, {name}?",
            "steps": []
        }

    try:
        app.log(f"Internet mode searching: {query}")
    except Exception:
        pass

    memory_parts = []

    try:
        memory_text = memory.memory_context_for_prompt(query, limit=12)
        if memory_text:
            memory_parts.append(str(memory_text))
    except Exception as e:
        _record_v3_error("web_fast_v2.memory_context", e)

    try:
        profile_text = brain.get_profile_context()
        if profile_text:
            memory_parts.append(str(profile_text))
    except Exception as e:
        _record_v3_error("web_fast_v2.profile_context", e)

    private_context = "\n\n".join(memory_parts)

    try:
        research = search_v4.research_with_precision(
            query,
            research_func=lambda q, max_results=8: app.web_research(
                q,
                max_results=max_results,
            ),
            max_results=getattr(app, "WEB_MAX_RESULTS", 8),
            max_attempts=5,
            use_ddgs_fallback=True,
        )

        web_data = research.get("web_data", {}) or {}
        diagnostics = research.get("diagnostics", {}) or {}

        try:
            app.log(search_v4.diagnostics_line(diagnostics))

            for attempt in diagnostics.get("attempts", []) or []:
                app.log(
                    "Search V4 attempt: "
                    f"provider={attempt.get('provider')}; "
                    f"query={attempt.get('query')}; "
                    f"relevant={attempt.get('relevant_results', 0) + attempt.get('relevant_pages', 0)}; "
                    f"precision={attempt.get('precision_satisfied', False)}"
                )
        except Exception:
            pass

        entity = str(diagnostics.get("entity", "") or "").strip()
        memory_matches = search_v3.context_mentions_entity(
            private_context,
            entity,
        )
        public_ok = bool(diagnostics.get("public_relevance_ok"))

        if not public_ok and not memory_matches:
            if entity:
                reply = (
                    f"I couldn't find reliable public information that actually matched "
                    f"'{entity}', {name}. I discarded unrelated results instead of guessing."
                )
            else:
                reply = (
                    f"I couldn't find enough relevant information to answer that reliably, {name}."
                )

            try:
                brain.note_reply(c, reply, was_web=True)
                memory.note_conversation_turn(
                    user_text=c,
                    assistant_text=reply,
                    tags=["web", "search_v4_failed"]
                )
                intelligence_v3.note_result(
                    c,
                    reply,
                    route="web_search_v4_failed",
                )
            except Exception:
                pass

            return {
                "mode": "chat",
                "reply": reply,
                "steps": [],
            }

        # Exact-fact questions get a deterministic precision pass before the
        # general summariser. This prevents "later this year" when the research
        # actually contains "November 19, 2026".
        precision_plan = search_v4.direct_precision_plan(
            c,
            web_data,
            spoken_name=name,
        )

        if precision_plan:
            try:
                reply = precision_plan.get("reply", "")
                source = precision_plan.get("_precision_source", "")
                score = precision_plan.get("_precision_score", 0.0)

                app.log(
                    f"Search V4 exact answer selected: score={score}; source={source}"
                )

                brain.note_reply(c, reply, was_web=True)
                memory.note_conversation_turn(
                    user_text=c,
                    assistant_text=reply,
                    tags=["web", "precision_v4"]
                )
                intelligence_v3.note_result(
                    c,
                    reply,
                    route="web_precision_v4",
                )
            except Exception:
                pass

            try:
                conversation_v4.note_reply(
                    precision_plan.get("reply", ""),
                    tool="web",
                    source_url=str(
                        precision_plan.get("_precision_source", "")
                        or ""
                    ),
                    entity=conversation_v4.guess_entity(c),
                    action="web",
                    action_target=c,
                )
            except Exception as e:
                _record_v3_error("conversation_v4.precision_web", e)

            precision_plan.pop("_precision_source", None)
            precision_plan.pop("_precision_score", None)
            return precision_plan

        try:
            web_context = (
                app.format_web_context(web_data)
                if public_ok
                else ""
            )
        except Exception as e:
            _record_v3_error("web_fast_v2.format_context", e)
            web_context = ""

        # Search V3's grounded summariser is still used for open-ended answers.
        # V4 passes richer diagnostics and better evidence into it.
        diagnostics["public_relevance_ok"] = public_ok

        web_plan = grounded_web_answer_v3(
            c,
            web_context,
            memory_context=private_context,
            search_diagnostics=diagnostics,
        )

        try:
            reply = web_plan.get("reply", "")
            brain.note_reply(c, reply, was_web=True)
            memory.note_conversation_turn(
                user_text=c,
                assistant_text=reply,
                tags=["web", "search_intelligence_v4"]
            )
            intelligence_v3.note_result(
                c,
                reply,
                route="web_search_v4",
            )
        except Exception as e:
            _record_v3_error("web_fast_v2.note_result", e)

        try:
            source_url = ""

            candidates = diagnostics.get(
                "precision_candidates",
                [],
            ) or []

            if candidates:
                source_url = str(
                    candidates[0].get("url", "")
                    or ""
                )

            if not source_url:
                for collection in (
                    web_data.get("results", []) or [],
                    web_data.get("pages", []) or [],
                ):
                    for item in collection:
                        if not isinstance(item, dict):
                            continue

                        source_url = str(
                            item.get("url")
                            or item.get("link")
                            or item.get("source_url")
                            or ""
                        ).strip()

                        if source_url:
                            break

                    if source_url:
                        break

            conversation_v4.note_reply(
                web_plan.get("reply", ""),
                tool="web",
                source_url=source_url,
                entity=conversation_v4.guess_entity(c),
                action="web",
                action_target=c,
            )
        except Exception as e:
            _record_v3_error("conversation_v4.web_result", e)

        return web_plan

    except Exception as e:
        _record_v3_error("web_fast_v2.search_intelligence_v4", e)

        try:
            app.log(f"Search Intelligence V4 failed: {e}")
        except Exception:
            pass

        return {
            "mode": "chat",
            "reply": (
                f"I couldn't complete the precision internet search right now, {name}."
            ),
            "steps": []
        }


def speak_v2(text):
    name = refresh_spoken_name()

    if SPEECH_STOP_REQUESTED.is_set():
        SPEECH_STOP_REQUESTED.clear()
        return

    cleaned = personality.clean_reply_text(text, name)

    try:
        context = brain.load_context()
        last_goal = context.get("last_user_goal", "")

        if str(cleaned).strip():
            brain.note_reply(last_goal, cleaned, was_web=should_use_web_search_v2(last_goal))
            memory.note_conversation_turn(user_text=last_goal, assistant_text=cleaned)
            intelligence_v3.note_result(last_goal, cleaned, route="spoken")
    except Exception:
        pass

    if SPEECH_STOP_REQUESTED.is_set():
        SPEECH_STOP_REQUESTED.clear()
        return

    return app_speak(cleaned)


def speak_worker_v2():
    """Same loop/queue/interrupt contract as jarvis_app.py's own
    speak_worker(), with Kokoro (via jarvis_claude_brain_v2) as the primary
    voice instead of Piper. Piper remains the fallback on any Kokoro
    failure, same layered-fallback pattern used everywhere else here.
    """
    while True:
        text = app.speak_queue.get()

        if text is None:
            break

        text = str(text).strip()

        if not text:
            app.speak_queue.task_done()
            continue

        # Never talk over you: a proactive, unsolicited line (network
        # health, code-change, update-check) could otherwise start
        # playing mid-sentence. A reply to your OWN command can't hit
        # this wait in practice -- transcription only starts once
        # you've already stopped talking. Capped so a stuck flag can
        # never silence Jarvis forever.
        app.ok_to_speak_event.wait(timeout=15.0)

        app.stop_talking_event.clear()
        app.speaking_now.set()

        try:
            app.log(f"Jarvis: {text}")
        except Exception:
            pass

        try:
            with app.tts_lock:
                claude_brain_v2.speak_kokoro_blocking(
                    text,
                    stop_event=app.stop_talking_event,
                )

        except Exception as e:
            try:
                app.log(f"Kokoro voice failed, falling back to Piper: {e}")
            except Exception:
                pass

            try:
                with app.tts_lock:
                    if app.PIPER_PYTHON_AVAILABLE:
                        app.stream_piper_voice(text)
                    else:
                        cached = app.prepare_voice_cache_cli(text)
                        app.play_wav_file(cached)
            except Exception as fallback_error:
                try:
                    app.log(f"Fallback voice also failed: {fallback_error}")
                except Exception:
                    pass

        finally:
            time.sleep(0.15)
            app.speaking_now.clear()
            app.stop_talking_event.clear()
            app.speak_queue.task_done()


def _plain_model_retry_v3(messages, goal, name):
    retry_messages = list(messages)
    retry_messages.append({
        "role": "system",
        "content": (
            "Your previous structured answer could not be parsed. Answer the user's request again "
            "as normal concise prose only. Do not output JSON, markdown fences or internal reasoning."
        ),
    })

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": app.OLLAMA_MODEL,
                "messages": retry_messages,
                "stream": False,
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.12,
                    "num_predict": 360,
                    "num_ctx": 4096,
                },
            },
            timeout=140,
        )
        response.raise_for_status()
        content = str(response.json().get("message", {}).get("content", "") or "")
        reply = intelligence_v3.extract_best_reply(content)
        if reply:
            return {"mode": "chat", "reply": reply, "steps": []}
    except Exception as e:
        _record_v3_error("ask_ai_plain_retry_v3", e)

    return None


# Fixed 150s timeout on claude_brain_v2.ask_sync() was cutting off
# genuine self-edit/coding work early -- CLAUDE.md's own mandated
# Change workflow (compile-check, run tests, broader regression tests)
# routinely takes longer than that for anything nontrivial. When
# ask_sync() times out, its own finally block resets the HUD's
# "thinking" state back to idle even though the underlying tool call
# may still be running -- looking exactly like "doesn't stay in
# thinking mode, looks like he's doing nothing". Detecting this class
# of request and giving it a much longer timeout fixes that without
# slowing down the fast path: ordinary conversation keeps the original
# 150s ceiling, so a genuinely broken/hung request still fails at a
# reasonable time instead of always waiting the long ceiling out.
_CODING_TASK_PATTERNS = (
    "fix yourself", "fix your code", "repair yourself", "self repair",
    "edit your", "edit yourself", "update your code", "update your own code",
    "change your code", "change your own code", "add to your own code",
    "change how you", "look at your code", "look at your own code",
    "debug yourself", "your own code", "modify your", "modify yourself",
    "rewrite your", "refactor your",
)

# Same failure this whole block was built to fix, just for a project
# Jarvis builds FOR the user instead of on himself: "make me a website"
# or a later "update the website" is real multi-file coding work, but
# without this it only ever got the generic 150s/medium-effort request
# ask_ai_common_v2 gives ordinary chat -- confirmed as the reported cause
# of "he just doesn't understand" when asked to update a website he'd
# already built. A build/update request that ran long enough to actually
# time out could also leave an orphaned request still running against
# the one shared Claude session in the background (see the cancel() in
# claude_brain_v2._run_coro), and the NEXT request -- e.g. that same
# "now update it" -- landing on top of it while it's still replying reads
# exactly like Claude "not understanding" a plain follow-up. Longer
# timeout keeps that collision from happening in the first place.
_PROJECT_BUILD_TARGETS = (
    "website", "web page", "webpage", "web app", "landing page",
    "app", "application", "program", "script", "game", "tool",
    # Game-dev/server-project phrasing specifically -- "help me code a
    # fivem server" or "build a minecraft plugin" contains none of the
    # words above (no "game", no "app"), so it fell through to ordinary
    # chat's 150s/medium-effort treatment exactly like "make a website"
    # once did before that got fixed. Real coding work either way.
    "server", "plugin", "mod", "datapack", "fivem", "minecraft",
    "discord bot", "resource pack",
)
_PROJECT_BUILD_VERBS = (
    "make", "build", "create", "update", "edit", "fix", "change",
    "add to", "improve", "redesign", "rewrite", "modify", "code",
    "help me", "help with", "write",
)

# Was 600s (10 minutes) -- confirmed too tight for "full blown website"
# or "fivem server" scale requests, which can genuinely run through many
# tool calls (plan, several files, styling, testing) well past that.
# Ordinary conversation is untouched -- this ceiling only ever applies
# once _looks_like_coding_task() below has already said yes.
CODING_TASK_TIMEOUT_SECONDS = 1800.0


# Reported live and reproduced: Jarvis offers to dig into his own code
# ("want me to trace the listening-indicator logic and fix it?"), the
# user replies with a short "yeah, please" -- and _looks_like_coding_task
# below only ever inspected the CURRENT utterance text, which contains
# none of its own trigger words. That short reply got the ordinary 150s
# timeout instead of the 1800s coding-task one, genuinely ran out of
# time mid-investigation, and fell through to the tool-less fallback
# brain -- which correctly (from its own narrow view) said it has no
# file access, but confusingly, since the user had just said yes to a
# real offer from what should have been the main brain. Same pattern
# jarvis_update_check_v1 and jarvis_claude_brain_v2's own destructive-
# action gate already use: a short affirmative shortly after an offer
# counts as accepting THAT offer, not a fresh, context-free utterance.
_CODING_OFFER_WINDOW_S = 60.0
_last_coding_offer_at = 0.0

_AFFIRMATIVE_RE = re.compile(
    r"^(yes|yeah|yep|yup|sure|do it|go ahead|go for it|please|"
    r"if you don.t mind|sounds good|okay|ok|proceed)\b", re.IGNORECASE,
)

# Loose on purpose -- this only needs to catch "I'm about to offer to do
# real engineering work", not classify precisely. False positives just
# mean a short "yes" shortly after gets the longer timeout it would
# have needed anyway if it WAS accepting a coding offer; false negatives
# are the actual reported bug.
_CODING_OFFER_PHRASE_RE = re.compile(
    r"\b(want me to|should i|shall i|i can|let me)\b.{0,60}\b"
    r"(code|fix|trace|dig into|debug|rewrite|edit|build|patch)\b",
    re.IGNORECASE,
)


def _note_possible_coding_offer(reply_text):
    global _last_coding_offer_at
    try:
        if _CODING_OFFER_PHRASE_RE.search(str(reply_text or "")):
            _last_coding_offer_at = time.time()
    except Exception:
        pass


def _looks_like_coding_task(text):
    t = str(text or "").lower()
    if any(phrase in t for phrase in _CODING_TASK_PATTERNS):
        return True
    if any(target in t for target in _PROJECT_BUILD_TARGETS):
        return any(verb in t for verb in _PROJECT_BUILD_VERBS)
    if (
        _AFFIRMATIVE_RE.match(str(text or "").strip())
        and (time.time() - _last_coding_offer_at) <= _CODING_OFFER_WINDOW_S
    ):
        return True
    return False


def ask_ai_common_v2(goal, original_func=None):
    name = refresh_spoken_name()

    prepared, resolved_normalized = prepare_command_v3(goal)
    resolved_goal = str(prepared.get("resolved_text") or prepared.get("clean_text") or goal)
    goal = resolved_goal

    raw_alias_result = aliases_v1.alias_command_fast(goal, name)
    if raw_alias_result:
        return finish_plan_v3(raw_alias_result, goal, name, "alias")

    if interrupt_v1.is_stop_command(goal):
        interrupt_v1.request_stop(app, reason="voice_stop")
        return {"mode": "chat", "reply": "", "steps": []}

    goal = aliases_v1.apply_aliases(goal)

    if desktop.is_stop_command(goal):
        stop_speaking_now()
        return {"mode": "action", "reply": "", "steps": []}

    try:
        learned_goal, rule = app.apply_learned_rule(goal)
    except Exception:
        learned_goal, rule = goal, None

    if rule:
        quick_result = quick_handle_command_v2(learned_goal)
        if quick_result:
            return quick_result
        goal = learned_goal

    # V3 routes every request through cleaned/resolved intent before local AI.
    quick_result = quick_handle_command_v2(goal)
    if quick_result:
        return quick_result

    # Belt-and-braces current-fact fallback. A freshness query must never reach
    # stale local knowledge just because a legacy classifier missed it.
    if intelligence_v3.needs_fresh_web(goal):
        web_result = web_fast_v2(goal)
        if web_result:
            return finish_plan_v3(web_result, goal, name, "web")

    try:
        memory_context_old = app.format_memory_context(goal)
    except Exception:
        memory_context_old = ""

    try:
        memory_context_v2 = memory.memory_context_for_prompt(goal, limit=10)
    except Exception:
        memory_context_v2 = ""

    messages = [
        {"role": "system", "content": get_system_prompt()},
        {"role": "system", "content": personality.style_prompt(name, goal)},
        {"role": "system", "content": brain.get_profile_context()},
        {"role": "system", "content": intelligence_v3.conversation_system_instruction(goal)},
    ]

    if memory_context_v2:
        messages.append({"role": "system", "content": memory_context_v2})

    if memory_context_old:
        messages.append({"role": "system", "content": memory_context_old})

    messages.append({"role": "user", "content": goal})

    try:
        brain_v2_prompt_parts = []
        if memory_context_v2:
            brain_v2_prompt_parts.append(str(memory_context_v2))
        if memory_context_old:
            brain_v2_prompt_parts.append(str(memory_context_old))

        if brain_v2_prompt_parts:
            brain_v2_prompt = (
                "[Background Jarvis already knows about the user/situation -- "
                "not something the user said, just context]\n"
                + "\n\n".join(brain_v2_prompt_parts)
                + f"\n\n[What the user actually said]\n{goal}"
            )
        else:
            brain_v2_prompt = goal

        if _looks_like_coding_task(goal):
            brain_v2_answer = provider_router.ask_active_brain(
                brain_v2_prompt, spoken_name=name, timeout=CODING_TASK_TIMEOUT_SECONDS, effort="high",
            )
        else:
            brain_v2_answer = provider_router.ask_active_brain(brain_v2_prompt, spoken_name=name)

        if brain_v2_answer.get("ok"):
            brain_v2_reply = str(brain_v2_answer.get("result", "") or "").strip()
            if brain_v2_reply:
                plan = personality.polish_plan(
                    {"mode": "chat", "reply": brain_v2_reply, "steps": []},
                    goal,
                    name,
                )
                _note_possible_coding_offer(plan.get("reply", ""))

                if plan.get("mode") == "chat" and (
                    intelligence_v3.is_low_value_reply(plan.get("reply", ""))
                    or brain.should_web_fallback(goal, plan.get("reply", ""))
                ):
                    fallback = web_fast_v2("search the internet for " + str(goal))
                    if fallback:
                        return finish_plan_v3(fallback, goal, name, "web_fallback")

                try:
                    reply = plan.get("reply", "")
                    memory.note_conversation_turn(user_text=goal, assistant_text=reply)
                    intelligence_v3.note_result(goal, reply, route="claude_brain_v2")
                    conversation_v4.note_reply(
                        reply,
                        tool="claude_brain_v2",
                        entity=conversation_v4.guess_entity(goal),
                        action="claude_brain_v2",
                        action_target=goal,
                    )
                except Exception as e:
                    _record_v3_error("ask_ai_common_v2.claude_brain_v2_note_turn", e)

                return plan
    except Exception as e:
        _record_v3_error("provider_router.ask_active_brain", e)

    if claude_v1.enabled():
        try:
            claude_context_parts = [
                get_system_prompt(),
                personality.style_prompt(name, goal),
                brain.get_profile_context(),
                intelligence_v3.conversation_system_instruction(goal),
            ]
            if memory_context_v2:
                claude_context_parts.append(memory_context_v2)
            if memory_context_old:
                claude_context_parts.append(memory_context_old)

            claude_answer = claude_v1.ask_chat(
                goal,
                spoken_name=name,
                context="\n\n".join(str(x) for x in claude_context_parts if x),
            )

            if claude_answer.get("ok"):
                claude_reply = str(claude_answer.get("result", "") or "").strip()
                if claude_reply:
                    plan = personality.polish_plan(
                        {"mode": "chat", "reply": claude_reply, "steps": []},
                        goal,
                        name,
                    )
                    _note_possible_coding_offer(plan.get("reply", ""))

                    if plan.get("mode") == "chat" and (
                        intelligence_v3.is_low_value_reply(plan.get("reply", ""))
                        or brain.should_web_fallback(goal, plan.get("reply", ""))
                    ):
                        fallback = web_fast_v2("search the internet for " + str(goal))
                        if fallback:
                            return finish_plan_v3(fallback, goal, name, "web_fallback")

                    try:
                        reply = plan.get("reply", "")
                        memory.note_conversation_turn(user_text=goal, assistant_text=reply)
                        intelligence_v3.note_result(goal, reply, route="claude_ai")
                        conversation_v4.note_reply(
                            reply,
                            tool="claude_ai",
                            entity=conversation_v4.guess_entity(goal),
                            action="claude_ai",
                            action_target=goal,
                        )
                    except Exception as e:
                        _record_v3_error("ask_ai_common_v2.claude_note_turn", e)

                    return plan
        except Exception as e:
            _record_v3_error("claude_v1.ask_chat", e)

    content = ""
    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": app.OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "format": "json",
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.15,
                    "num_predict": 320,
                    "num_ctx": 4096,
                },
            },
            timeout=140,
        )

        response.raise_for_status()
        content = str(response.json().get("message", {}).get("content", "") or "")
        plan = response_v2.parse_model_plan(content, name=name, command=goal)

        # Response V2 deliberately returns a friendly generic sentence when it
        # receives valid-but-unexpected JSON. V3 first salvages any answer-like
        # field, then performs one plain-prose retry instead of exposing that
        # parser failure to the user.
        if intelligence_v3.is_low_value_reply(plan.get("reply", "")):
            recovered = intelligence_v3.extract_best_reply(content)
            if recovered and not intelligence_v3.is_low_value_reply(recovered):
                plan = {"mode": "chat", "reply": recovered, "steps": []}
            else:
                retry_plan = _plain_model_retry_v3(messages, goal, name)
                if retry_plan:
                    plan = retry_plan

    except Exception as e:
        _record_v3_error("ask_ai_common_v2", e)
        if original_func:
            try:
                plan = original_func(goal)
            except Exception as inner:
                _record_v3_error("ask_ai_common_v2.original_fallback", inner)
                retry_plan = _plain_model_retry_v3(messages, goal, name)
                if retry_plan:
                    plan = retry_plan
                else:
                    raise
        else:
            retry_plan = _plain_model_retry_v3(messages, goal, name)
            if retry_plan:
                plan = retry_plan
            else:
                raise

    plan = personality.polish_plan(plan, goal, name)

    if plan.get("mode") == "chat" and (
        intelligence_v3.is_low_value_reply(plan.get("reply", ""))
        or brain.should_web_fallback(goal, plan.get("reply", ""))
    ):
        fallback = web_fast_v2("search the internet for " + str(goal))
        if fallback:
            return finish_plan_v3(fallback, goal, name, "web_fallback")

    try:
        reply = plan.get("reply", "")
        memory.note_conversation_turn(user_text=goal, assistant_text=reply)
        intelligence_v3.note_result(goal, reply, route="local_ai")
    except Exception as e:
        _record_v3_error("ask_ai_common_v2.note_turn", e)

    return plan

def ask_ai_v2(goal):
    return ask_ai_common_v2(goal, _original_ask_ai)


def ask_ai_chat_v2(goal):
    return ask_ai_common_v2(goal, _original_ask_ai_chat)


def run_agent_task_v2(goal, *args, **kwargs):
    original_goal = str(goal)

    try:
        prepared, normalized_goal = prepare_command_v3(original_goal)
        resolved_goal = str(prepared.get("resolved_text") or original_goal)
        normalized_goal = app_normalise(resolved_goal)

        if intelligence_v3.normalise(original_goal) != intelligence_v3.normalise(resolved_goal):
            try:
                app.log(f"Intelligence V3 follow-up used: {original_goal} -> {resolved_goal}")
            except Exception:
                pass

        original_goal = resolved_goal
    except Exception as e:
        _record_v3_error("run_agent_task_v2.prepare", e)
        normalized_goal = app_normalise(original_goal)

    if desktop.is_stop_command(normalized_goal):
        stop_speaking_now()
        return

    try:
        brain.note_user_goal(normalized_goal)
        memory.note_conversation_turn(user_text=normalized_goal)
    except Exception as e:
        _record_v3_error("run_agent_task_v2.context", e)
        try:
            app.log(f"Memory/Intelligence V3 context failed: {e}")
        except Exception:
            pass

    if _original_run_agent_task:
        try:
            return _original_run_agent_task(original_goal, *args, **kwargs)
        except TypeError:
            return _original_run_agent_task(original_goal)

    app_speak(f"I could not start the main Jarvis task runner, {refresh_spoken_name()}.")

_PUSH_TO_TALK_INSTALLED = False
_PTT_STATE = {"active": False}
_PTT_LOCK = threading.Lock()


def _ptt_capture_and_run():
    """Real push-to-talk, using backtalk's own unmodified record_held():
    "record raw audio while is_held() is True, then transcribe. The
    button is the VAD -- no endpointing." (backtalk/ears.py's own words.)

    This hands the microphone off rather than running two capture
    systems at once: Jarvis's own continuous Whisper listener has to
    fully close its input stream before backtalk's ears opens its own,
    because two simultaneous open input streams on the same device is
    exactly what caused real audio conflicts earlier in this project
    (documented in fullstack_agent_migration_receipt.json). Wrapped in
    try/finally throughout so a crash mid-capture can never leave Jarvis
    permanently deaf -- his own listener always comes back.
    """
    was_listening = False
    try:
        import keyboard
        from backtalk import ears as backtalk_ears

        was_listening = app.listening_enabled.is_set()

        if was_listening:
            app.listening_enabled.clear()
            # voice_listener_loop polls its queue with a 0.2s timeout
            # before it notices the flag and exits its `with` block
            # (which is what actually closes the stream) -- wait past
            # that with margin before opening a second stream.
            time.sleep(0.5)

        app.set_face_state("listening")
        try:
            transcript = backtalk_ears.record_held(
                is_held=lambda: keyboard.is_pressed("home"),
            )
        finally:
            app.set_face_state("idle")

        if transcript:
            try:
                app.log(f"Push-to-talk heard: {transcript}")
            except Exception:
                pass
            # run_agent_task() already treats its input as a confirmed
            # command with no wake-word check of its own (that check
            # lives one level up, in voice_listener_loop) -- exactly the
            # real push-to-talk contract: holding the key IS the
            # confirmation, so no need to also say "Jarvis".
            app.run_agent_task(transcript)
    except Exception as e:
        try:
            app.log(f"Push-to-talk capture failed: {e}")
        except Exception:
            pass
    finally:
        if was_listening:
            try:
                app.listening_enabled.set()
                threading.Thread(
                    target=app.voice_listener_loop,
                    args=(lambda *a, **k: None,),
                    daemon=True,
                ).start()
            except Exception as e:
                try:
                    app.log(f"Push-to-talk: failed to resume the wake-word listener: {e}")
                except Exception:
                    pass

        with _PTT_LOCK:
            _PTT_STATE["active"] = False


def _install_push_to_talk_v2():
    """Hold Home to talk, alongside saying "Jarvis" -- brought back using
    backtalk's own real, unmodified push-to-talk capture (record_held in
    backtalk/ears.py), not an approximation built on Jarvis's existing
    wake-word/conversation-mode machinery. backtalk's real design has no
    wake-word concept at all (it's push-to-talk OR always-listening, one
    or the other) -- the wake word stays because the user asked to keep
    it, layered on top by handing the mic between the two systems rather
    than running them at once.

    Also interrupts Jarvis mid-reply on press (same stop_current_speech()
    the "say Jarvis while he speaks" barge-in already uses), so a
    long-winded answer can be cut off by holding Home instead of only by
    saying the wake word again.
    """
    global _PUSH_TO_TALK_INSTALLED

    if _PUSH_TO_TALK_INSTALLED:
        return

    try:
        import keyboard

        def _on_home_press(event=None):
            try:
                if app.speaking_now.is_set():
                    app.stop_current_speech()
            except Exception:
                pass

            with _PTT_LOCK:
                if _PTT_STATE["active"]:
                    return  # already capturing this hold; key-repeat re-firing
                _PTT_STATE["active"] = True

            threading.Thread(target=_ptt_capture_and_run, daemon=True).start()

        keyboard.on_press_key("home", _on_home_press, suppress=False)
        _PUSH_TO_TALK_INSTALLED = True

        try:
            app.log("Push-to-talk ready: hold Home to talk (also interrupts Jarvis mid-reply).")
        except Exception:
            pass
    except Exception as e:
        try:
            app.log(f"Push-to-talk hotkey failed: {e}")
        except Exception:
            pass


def _uninstall_push_to_talk_v2():
    """Reverses _install_push_to_talk_v2() live, for the communication-
    mode toggle -- unhooks the Home key so it stops acting as a PTT
    trigger, and resets the guard so re-enabling PTT later works again."""
    global _PUSH_TO_TALK_INSTALLED

    if not _PUSH_TO_TALK_INSTALLED:
        return

    try:
        import keyboard
        keyboard.unhook_key("home")
    except Exception:
        pass

    _PUSH_TO_TALK_INSTALLED = False


def apply_communication_mode(mode):
    """Live-applies a communication-mode change from the UI toggle
    (push-to-talk only / wake word only / both) without needing a
    restart. Persists the choice first so it also sticks on the next
    launch, then starts or stops each of the two independent listening
    systems using the exact same hand-off primitives push-to-talk
    already uses internally (app.listening_enabled + a fresh
    voice_listener_loop thread for wake word, keyboard hook install/
    unhook for push-to-talk)."""
    if mode not in ("ptt", "wake_word", "both"):
        return False

    try:
        settings_v1.save_communication_mode(mode)
    except Exception:
        pass

    wake_word_wanted = mode in ("wake_word", "both")
    ptt_wanted = mode in ("ptt", "both")

    try:
        wake_word_running = app.listening_enabled.is_set()
    except Exception:
        wake_word_running = False

    if wake_word_wanted and not wake_word_running:
        try:
            app.listening_enabled.set()
            threading.Thread(
                target=app.voice_listener_loop,
                args=(lambda *a, **k: None,),
                daemon=True,
            ).start()
        except Exception as e:
            try:
                app.log(f"Couldn't start the wake-word listener: {e}")
            except Exception:
                pass
    elif not wake_word_wanted and wake_word_running:
        try:
            app.listening_enabled.clear()
        except Exception:
            pass

    if ptt_wanted:
        _install_push_to_talk_v2()
    else:
        _uninstall_push_to_talk_v2()

    try:
        labels = {"ptt": "push-to-talk only", "wake_word": "wake word only", "both": "push-to-talk and wake word"}
        app.log(f"Communication mode set to {labels[mode]}.")
    except Exception:
        pass

    return True


COMMUNICATION_MODE_FLAG = Path(r"C:\AI-Agent\.communication_mode_changed")
BRAIN_SWITCH_ANNOUNCE_FLAG = Path(r"C:\AI-Agent\.brain_switch_announce")
_comm_mode_watch_started = False


def _communication_mode_watch_loop():
    """The HUD's mode dropdown (ai-visualizer/core.js) runs inside
    jarvis_remote_chat.py's own process, not this one -- same cross-
    process gap VOICE_REFRESH_FLAG already bridges for ElevenLabs
    settings. Polls for that settings save, cheap enough (a
    Path.exists() every couple seconds) to just run for the process's
    whole life rather than needing to be threaded through every call
    site the way a per-utterance check would. Also covers the HUD's
    brain-picker dropdown (same cross-process gap, same fix) -- real
    reported bug: switching brains changed the setting fine but never
    told the user out loud, so a failed switch (Ollama not ready) looked
    identical to a successful one from the HUD alone."""
    while True:
        try:
            if COMMUNICATION_MODE_FLAG.exists():
                try:
                    COMMUNICATION_MODE_FLAG.unlink()
                except Exception:
                    pass
                apply_communication_mode(settings_v1.get_communication_mode())
        except Exception:
            pass

        try:
            # Rename-then-read rather than read-then-delete: a plain
            # exists()/read/unlink sequence let the confirmation get
            # spoken twice in a row on a live test (exact cause not
            # pinned down -- possibly this machine's still-unsolved
            # duplicate-process quirk, possibly a plain poll-timing
            # race). Renaming is atomic regardless of which it is: only
            # one caller ever wins it, so only one ever speaks.
            claimed_path = BRAIN_SWITCH_ANNOUNCE_FLAG.with_suffix(".claimed")
            BRAIN_SWITCH_ANNOUNCE_FLAG.rename(claimed_path)
            provider_id = claimed_path.read_text(encoding="utf-8").strip()
            try:
                claimed_path.unlink()
            except Exception:
                pass
            if provider_id == "ollama":
                app.speak(f"Switched to my local Qwen model, {refresh_spoken_name()} -- running right here on your PC.")
            elif provider_id == "claude":
                app.speak(f"Switched back to Claude, {refresh_spoken_name()} -- that's my primary brain.")
        except FileNotFoundError:
            pass
        except Exception:
            pass

        time.sleep(2)


def _start_communication_mode_watch():
    global _comm_mode_watch_started
    if _comm_mode_watch_started:
        return
    _comm_mode_watch_started = True
    threading.Thread(target=_communication_mode_watch_loop, daemon=True).start()


def _lower_process_priority():
    """Windows gives every process the same NORMAL scheduling priority by
    default, so under real CPU contention (a game maxing out every core)
    the OS scheduler treats Jarvis's background threads as equally
    important as the game's own -- a real, unnecessary contributor to
    "gaming lags when Jarvis does something." BELOW_NORMAL is a pure
    scheduling hint: it doesn't throttle Jarvis when the CPU is idle
    (the overwhelming majority of the time), it just tells Windows to
    prefer the foreground app first when both actually want the same
    CPU core at once. Applies to every Jarvis process that calls
    install_v2() (the main app and jarvis_remote_chat.py's headless
    install both do), each setting its own priority -- best-effort, a
    machine without pywin32 available just skips this silently."""
    try:
        import win32api
        import win32process
        handle = win32api.GetCurrentProcess()
        win32process.SetPriorityClass(handle, win32process.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def install_v2(headless=False):
    """headless=True is for jarvis_remote_chat.py: it only needs the
    ask_ai_common_v2/quick_handle_command_v2 overrides and the
    availability flags they read -- never the desktop-only side effects
    (global hotkeys via the `keyboard` hook, the face-window subprocess
    launch, the JarvisApp/speak GUI swaps). Those matter because the
    remote server calls this from a background HTTP worker thread, not
    the main thread, and installing a low-level Windows keyboard hook
    off the main thread is what hung the whole server the first time
    this shipped -- every request blocked on the same install lock
    behind it, forever."""
    _lower_process_priority()
    refresh_spoken_name()

    try:
        maintainer_v1.install_error_hooks()
    except Exception:
        pass


    if not headless:
        try:
            interrupt_v1.install_hotkey(app, hotkey="ctrl+alt+j")
        except Exception:
            pass

    app.BRAIN_V2_AVAILABLE = True
    app.MEMORY_V2_AVAILABLE = True
    app.PERSONALITY_V2_AVAILABLE = True
    app.DESKTOP_V2_AVAILABLE = True
    app.OPERATOR_V1_AVAILABLE = True
    app.OPERATOR_V2_AVAILABLE = True
    app.PC_CONTROL_V3_AVAILABLE = True
    app.CREATIVE_V2_AVAILABLE = True
    app.ATTACHMENTS_V1_AVAILABLE = True
    app.GOAL_MODE_V32_AVAILABLE = True
    app.INTELLIGENCE_CORE_V3_AVAILABLE = True
    app.SEARCH_INTELLIGENCE_V3_AVAILABLE = True
    app.SEARCH_INTELLIGENCE_V4_AVAILABLE = True
    app.LINK_INTELLIGENCE_V1_AVAILABLE = True
    app.TOOL_INTELLIGENCE_V1_AVAILABLE = True
    app.CONVERSATION_INTELLIGENCE_V4_AVAILABLE = True

    if _original_quick_handle_command:
        app.quick_handle_command = quick_handle_command_v2

    app.should_use_web_search = should_use_web_search_v2
    app.clean_web_query = clean_web_query_v2

    if _original_answer_with_web_context:
        app.answer_with_web_context = answer_with_web_context_v2

    if _original_web_fast:
        app.web_fast = web_fast_v2

    if not headless:
        if _original_speak:
            app.speak = speak_v2

        if _original_speak_worker:
            app.speak_worker = speak_worker_v2

        if _original_JarvisApp:
            app.JarvisApp = _HiddenJarvisApp_v2

    if _original_log:
        app.log = _log_to_file_v2

    if not headless:
        app.apply_communication_mode = apply_communication_mode
        _start_communication_mode_watch()

        try:
            _startup_comm_mode = settings_v1.get_communication_mode()
        except Exception:
            _startup_comm_mode = "both"

        if _startup_comm_mode in ("ptt", "both"):
            _install_push_to_talk_v2()

    if _original_ask_ai:
        app.ask_ai = ask_ai_v2

    if _original_ask_ai_chat:
        app.ask_ai_chat = ask_ai_chat_v2

    if _original_run_agent_task:
        app.run_agent_task = run_agent_task_v2

    try:
        app.WEB_ANSWER_PROMPT = brain.web_answer_prompt(refresh_spoken_name())
    except Exception:
        pass

    try:
        app.log(f"Search Intelligence V3 + Intelligence Core V3 + Brain V2 + Memory V2 + Personality V2 + Desktop V2 + Operator V2.1 + PC Control V3.1 + Creative V2 + Attachments V1 loaded. Mode: {personality.mode_label()}. Name: {refresh_spoken_name()}")
    except Exception:
        pass

    if headless:
        return

    try:
        claude_brain_v2.reset_face_state()
    except Exception:
        pass

    _launch_visualizer_face_v2()
    _launch_remote_chat_v2()
    _launch_mini_bar_v2()
    _launch_onboarding_wizard_v2()

    try:
        claude_brain_v2.prewarm_voice_async()
    except Exception:
        pass

    try:
        claude_brain_v2.prewarm_brain_async()
    except Exception:
        pass

    try:
        claude_brain_v2.prewarm_ptt_async()
    except Exception:
        pass

    try:
        threading.Thread(
            target=update_check_v1.background_check_loop,
            args=(app, refresh_spoken_name),
            daemon=True,
        ).start()
    except Exception:
        pass

    try:
        threading.Thread(
            target=govee_v1.background_new_device_check_loop,
            args=(app, refresh_spoken_name),
            daemon=True,
        ).start()
    except Exception:
        pass

    # DISABLED AGAIN (2026-09-10), for real this time. Tried a real fix
    # (8s detection instead of 45s, graceful terminate() before any hard
    # kill) and re-enabled it -- still reproducibly took the whole
    # process down within seconds, multiple times, even with those
    # improvements. Also added a genuine root-cause attempt (the
    # single-instance lock now runs FIRST, before install_v2() does any
    # real work) which did NOT stop the duplicate from fully spawning
    # either -- strong evidence the duplication happens via something
    # that bypasses this process's own TCP-port lock entirely (most
    # likely a sandboxing/AV mechanism giving the shadow copy its own
    # virtualized network stack, so the "port already in use" check
    # never actually collides). Given kill-based cleanup keeps crashing
    # the machine and even a same-process, checked-early lock doesn't
    # stop the duplication, this needs Process Monitor / real-time-
    # protection-disabled diagnosis in a dedicated session, not more
    # live guessing under time pressure. Stability wins for now --
    # the GPU-contention/lag problem stays open, unsolved, tracked here.
    # try:
    #     threading.Thread(
    #         target=process_dedup_v1.background_dedup_loop,
    #         args=(app,),
    #         daemon=True,
    #     ).start()
    # except Exception:
    #     pass


def _launch_visualizer_face_v2():
    """Start the JARVIS face: jarvis_face_window.py opens ai-visualizer's
    server (if not already running), opens it as a standalone app-like
    window via Edge app mode (no tabs/address bar), and holds a system
    tray icon for the rest of the process's life so Jarvis stays visibly
    "running in the background" after that window is closed.

    Deliberately a plain script (python.exe/pythonw.exe), not a compiled
    exe. Two separate PyInstaller builds of an earlier version of this
    launcher (a pywebview-based native window, then a bare Edge-app-mode
    launcher with no GUI toolkit at all) both produced a confirmed
    runaway process-spawn loop (40+ stray processes within seconds) when
    launched from Jarvis's own process tree -- the second build ruled out
    pywebview as the cause. Plain scripts (this call, and this exact
    server.py) have relaunched safely under the same still-unidentified
    environment quirk all session (documented in
    fullstack_agent_migration_receipt.json), stabilizing at one relaunch
    rather than cascading, so this stays a script. It also carries its
    own single-instance guard (a port bind, checked before anything else)
    as a second layer of safety, verified stable over 25+ seconds before
    being wired in here.
    """
    try:
        subprocess.Popen(
            [sys.executable, "jarvis_face_window.py"],
            cwd=r"C:\AI-Agent",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        try:
            app.log(f"JARVIS face window failed to start: {e}")
        except Exception:
            pass


def _launch_onboarding_wizard_v2():
    """First-launch welcome wizard (Phase 2). Cheap to call every startup
    -- jarvis_onboarding_v1.main() checks should_show_wizard() itself and
    exits immediately for every existing/already-configured install, so
    this is a no-op subprocess spawn-and-exit on the common path, not a
    real cost. Plain-script launch, same reasoning as the face window."""
    try:
        subprocess.Popen(
            [sys.executable, "jarvis_onboarding_v1.py"],
            cwd=r"C:\AI-Agent",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        try:
            app.log(f"Onboarding wizard failed to start: {e}")
        except Exception:
            pass


def _launch_mini_bar_v2():
    """Start jarvis_mini_bar.py -- the small click-through bar that
    hovers above the taskbar while actively talking to Jarvis. Same
    plain-script + own single-instance guard pattern as the face window
    and remote-chat launchers above, for the same reason (frozen exes
    hit a confirmed relaunch-storm bug on this machine; plain scripts
    haven't)."""
    try:
        subprocess.Popen(
            [sys.executable, "jarvis_mini_bar.py"],
            cwd=r"C:\AI-Agent",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        try:
            app.log(f"JARVIS mini bar failed to start: {e}")
        except Exception:
            pass


def _launch_remote_chat_v2():
    """Start jarvis_remote_chat.py -- the Tailscale-only remote voice/text
    chat server -- if it isn't already listening on its port. Single
    instance is enforced by trying to bind the port ourselves first and
    releasing it immediately; if that fails, something (almost certainly
    our own server from a previous launch) already owns it, so skip."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 8792))
        s.close()
    except OSError:
        return  # already running

    try:
        subprocess.Popen(
            [sys.executable, "jarvis_remote_chat.py"],
            cwd=r"C:\AI-Agent",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        try:
            app.log(f"Remote chat server failed to start: {e}")
        except Exception:
            pass


if __name__ == "__main__":
    # THE actual root cause of the whole "10 processes running, GPU
    # contention, lag/freezing" saga: this check existed in jarvis_app.py
    # all along (app.main()'s own first line), but app.main() only runs
    # at the very END of this block -- AFTER install_v2() had already
    # unconditionally spawned every satellite (face window, mini bar,
    # remote chat, the visualizer server) and started every background
    # thread, real duplicate or not. A genuine second launch of this
    # script was never actually stopped from doing all of that expensive,
    # duplicative work; it only got turned away from the final blocking
    # main loop, by which point two fully independent, fully-functional
    # Jarvis sessions were already alive and fighting over the same mic,
    # speakers, and GPU. Checking here, first, means a real duplicate
    # exits immediately -- no models loaded, no satellites spawned, no
    # background threads started, nothing for it to contend with the
    # real instance over.
    if not app.ensure_single_instance():
        raise SystemExit(0)

    install_v2()

    try:
        ui.install_ui_v2(app)
    except Exception as e:
        print(f"UI V2 failed to install: {e}")

    try:
        ui3.install_ui_v3(app)
    except Exception as e:
        print(f"UI V3 failed to install: {e}")

    if hasattr(app, "main"):
        app.main()
    else:
        raise RuntimeError("Your jarvis_app.py has no main() function. Restore the working ZIP first.")
