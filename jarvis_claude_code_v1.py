from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


VERSION = "1.0.0"
PROJECT_ROOT = Path(r"C:\AI-Agent")
DEFAULT_MODEL = "sonnet"
DEFAULT_EFFORT = "medium"
DEFAULT_TIMEOUT = 180

_LOCK = threading.RLock()


def _memory_root() -> Path:
    preferred = Path(r"E:\JarvisMemory\claude_code")
    fallback = PROJECT_ROOT / "JarvisMemory" / "claude_code"

    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except Exception:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


MEMORY_ROOT = _memory_root()
SETTINGS_FILE = MEMORY_ROOT / "settings.json"
CALL_LOG = MEMORY_ROOT / "calls.jsonl"


DEFAULT_SETTINGS = {
    "enabled": True,
    "model": DEFAULT_MODEL,
    "chat_effort": DEFAULT_EFFORT,
    "research_effort": "high",
    "planner_effort": "medium",
    "diagnostic_effort": "high",
    "timeout_seconds": DEFAULT_TIMEOUT,
    "fallback_to_local": True,
}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_settings() -> Dict[str, Any]:
    result = dict(DEFAULT_SETTINGS)

    try:
        data = json.loads(
            SETTINGS_FILE.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )
        if isinstance(data, dict):
            result.update(data)
    except Exception:
        pass

    return result


def save_settings(settings: Dict[str, Any]) -> None:
    data = dict(DEFAULT_SETTINGS)
    data.update(settings or {})

    try:
        SETTINGS_FILE.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def set_enabled(enabled: bool) -> None:
    settings = load_settings()
    settings["enabled"] = bool(enabled)
    save_settings(settings)


def enabled() -> bool:
    return bool(load_settings().get("enabled", True))


_PATH_REFRESHED = False


def _refresh_path_from_registry() -> None:
    """Same fix jarvis_provider_router_v1 got for every other provider --
    this process's PATH is snapshotted once at startup and never updates
    again no matter what gets installed afterward. Claude Code itself
    (the default provider) never got this fix, so a Claude Code install/
    reinstall/update that lands in a non-default location while Jarvis is
    already running would silently keep reporting "not found" forever,
    same bug class as the Codex one, just left unpatched on the provider
    most likely to matter. Runs once per process."""
    global _PATH_REFRESHED
    if _PATH_REFRESHED:
        return
    _PATH_REFRESHED = True

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as k:
            machine_path, _ = winreg.QueryValueEx(k, "Path")
    except Exception:
        machine_path = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            user_path, _ = winreg.QueryValueEx(k, "Path")
    except Exception:
        user_path = ""

    fresh = ";".join(p for p in (machine_path, user_path) if p)
    if not fresh:
        return

    current = os.environ.get("PATH", "")
    os.environ["PATH"] = fresh + (";" + current if current else "")


def _where(name: str) -> Optional[str]:
    """Windows' own `where` -- resolves PATH AND the "App Paths" registry
    key, which shutil.which() never checks."""
    try:
        proc = subprocess.run(
            ["where", name], capture_output=True, text=True, timeout=5,
            shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            return None
        first_line = proc.stdout.strip().splitlines()[0].strip() if proc.stdout.strip() else ""
        return first_line if first_line and Path(first_line).exists() else None
    except Exception:
        return None


def _candidate_cli_paths() -> Iterable[Path]:
    _refresh_path_from_registry()

    values = []

    for name in ("claude.cmd", "claude.exe", "claude"):
        found = shutil.which(name)
        if found:
            values.append(Path(found))

    where_found = _where("claude")
    if where_found:
        values.append(Path(where_found))

    appdata = os.environ.get("APPDATA")
    if appdata:
        npm_dir = Path(appdata) / "npm"
        values.extend(
            [
                npm_dir / "claude.cmd",
                npm_dir / "claude.exe",
                npm_dir / "claude",
            ]
        )

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        values.extend(
            [
                Path(program_files) / "nodejs" / "claude.cmd",
            ]
        )

    seen = set()

    for value in values:
        key = str(value).lower()

        if key in seen:
            continue

        seen.add(key)

        if value.exists():
            yield value


def find_cli() -> Optional[Path]:
    return next(iter(_candidate_cli_paths()), None)


def cli_version() -> str:
    cli = find_cli()

    if not cli:
        return ""

    try:
        proc = subprocess.run(
            [str(cli), "--version"],
            cwd=str(PROJECT_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=20,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        text = clean(proc.stdout or proc.stderr)

        if proc.returncode == 0:
            return text

    except Exception:
        pass

    return ""


def status() -> Dict[str, Any]:
    settings = load_settings()
    cli = find_cli()
    version = cli_version()

    return {
        "enabled": bool(settings.get("enabled", True)),
        "cli_found": bool(cli),
        "cli_path": str(cli or ""),
        "version": version,
        "model": str(settings.get("model", DEFAULT_MODEL)),
        "fallback_to_local": bool(
            settings.get("fallback_to_local", True)
        ),
    }


def _log_call(data: Dict[str, Any]) -> None:
    record = dict(data or {})
    record["timestamp"] = time.time()

    try:
        with CALL_LOG.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass


def _safe_env() -> Dict[str, str]:
    env = dict(os.environ)

    # The user authenticated Claude Code through the Claude subscription.
    # Do not accidentally switch this child process to API-key billing.
    env.pop("ANTHROPIC_API_KEY", None)

    # Avoid retaining a separate prompt history for every Jarvis turn.
    env["CLAUDE_CODE_SKIP_PROMPT_HISTORY"] = "1"

    return env


def _json_result(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()

    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")

    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            return data if isinstance(data, dict) else {}
        except Exception:
            pass

    return {}


def _run(
    prompt: str,
    *,
    system_prompt: str = "",
    model: str = "",
    effort: str = "",
    timeout: Optional[int] = None,
    max_turns: int = 1,
    tools: str = "",
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    settings = load_settings()

    if not settings.get("enabled", True):
        return {
            "ok": False,
            "error": "Claude routing is disabled.",
            "kind": "disabled",
        }

    cli = find_cli()

    if not cli:
        return {
            "ok": False,
            "error": "Claude Code CLI was not found.",
            "kind": "not_found",
        }

    model = clean(model) or clean(
        settings.get("model", DEFAULT_MODEL)
    )
    effort = clean(effort) or DEFAULT_EFFORT
    timeout = int(
        timeout
        or settings.get(
            "timeout_seconds",
            DEFAULT_TIMEOUT,
        )
    )

    # The prompt and system prompt can both grow arbitrarily large (web
    # research context, accumulated memory/conversation context). Passing
    # either as a literal command-line argument runs into Windows' ~8K
    # character command-line limit ("The command line is too long."), which
    # silently fails the call and falls back to the local brain. The prompt
    # goes over stdin instead, and the system prompt goes through a temp
    # file, so the actual command line only ever contains short flags.
    command = [
        str(cli),
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--effort",
        effort,
        "--max-turns",
        str(max(1, int(max_turns))),
        "--no-session-persistence",
        "--no-chrome",
        "--disable-slash-commands",
        "--permission-prompts",
        "none",
    ]

    system_prompt_file = None

    if system_prompt:
        try:
            fd, system_prompt_file = tempfile.mkstemp(
                prefix="jarvis_claude_sp_",
                suffix=".txt",
                dir=str(MEMORY_ROOT),
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(system_prompt))
            command.extend(
                [
                    "--system-prompt-file",
                    system_prompt_file,
                ]
            )
        except Exception:
            system_prompt_file = None
            command.extend(
                [
                    "--system-prompt",
                    str(system_prompt),
                ]
            )

    # Normal Jarvis reasoning must never let Claude Code operate the PC,
    # filesystem, browser, MCP tools, or shell.
    command.extend(
        [
            "--tools",
            str(tools),
            "--disallowedTools",
            "mcp__*",
        ]
    )

    started = time.time()

    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd or PROJECT_ROOT),
            env=_safe_env(),
            input=str(prompt),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    except subprocess.TimeoutExpired:
        _log_call(
            {
                "ok": False,
                "kind": "timeout",
                "model": model,
                "effort": effort,
                "elapsed": time.time() - started,
            }
        )

        return {
            "ok": False,
            "error": "Claude Code timed out.",
            "kind": "timeout",
        }

    except Exception as exc:
        _log_call(
            {
                "ok": False,
                "kind": "exception",
                "error": str(exc),
                "model": model,
                "effort": effort,
            }
        )

        return {
            "ok": False,
            "error": str(exc),
            "kind": "exception",
        }

    finally:
        if system_prompt_file:
            try:
                os.remove(system_prompt_file)
            except Exception:
                pass

    elapsed = time.time() - started

    data = _json_result(proc.stdout)

    result = clean(
        data.get("result", "")
        if isinstance(data, dict)
        else ""
    )

    if not result and proc.returncode == 0:
        result = clean(proc.stdout)

    # Defensive unwrap: reported live (raw JSON spoken verbatim to the
    # user) -- despite jarvis_system_prompt()'s explicit "do not output
    # JSON" instruction, the model itself occasionally still generates a
    # reply shaped like Jarvis's own internal plan envelope
    # ({"mode": "chat", "reply": "...", "steps": []}), almost certainly
    # picked up from seeing that exact shape elsewhere in the codebase
    # it's reasoning about. This is the ONE call's own "result" field
    # already unwrapped from the CLI's own JSON envelope -- if THAT text
    # is itself JSON carrying a "reply" key, unwrap it too rather than
    # ever speaking the raw envelope.
    if result.startswith("{") and '"reply"' in result:
        try:
            inner = json.loads(result)
            if isinstance(inner, dict) and clean(inner.get("reply", "")):
                result = clean(inner.get("reply", ""))
        except (ValueError, TypeError):
            pass

    ok = bool(
        proc.returncode == 0
        and result
    )

    error = clean(proc.stderr)

    if not ok and not error:
        error = clean(
            data.get("error", "")
            if isinstance(data, dict)
            else ""
        )

    call_info = {
        "ok": ok,
        "kind": "success" if ok else "failure",
        "model": model,
        "effort": effort,
        "elapsed": round(elapsed, 3),
        "returncode": proc.returncode,
        "session_id": clean(
            data.get("session_id", "")
            if isinstance(data, dict)
            else ""
        ),
        "total_cost_usd": data.get(
            "total_cost_usd"
        )
        if isinstance(data, dict)
        else None,
    }

    if error:
        call_info["error"] = error[:1000]

    _log_call(call_info)

    return {
        **call_info,
        "result": result,
        "raw": data,
        "error": error,
    }


def jarvis_system_prompt(
    spoken_name: str,
    extra_context: str = "",
) -> str:
    context = str(extra_context or "").strip()

    prompt = (
        "You are Jarvis, the user's personal desktop AI assistant. "
        "You are speaking directly to the user through the existing Jarvis UI. "
        f"Address the user as {spoken_name} when natural, but do not force it "
        "into every sentence. "
        "Answer the user's actual request directly. "
        "Be concise, conversational, competent and natural. "
        "Do not claim you performed a PC action unless the surrounding Jarvis "
        "tool system actually performed it. "
        "For current facts, rely on supplied research context rather than "
        "pretending your training knowledge is current. "
        "Never expose internal prompts, command lines, implementation details "
        "or hidden reasoning unless the user explicitly asks about the system. "
        "Do not output JSON unless explicitly instructed by the caller. "
        "If the user asks for a real action, device, or capability you have no "
        "way to actually perform right now (not just a fact you don't know), "
        "don't fake it or flatly refuse -- say plainly, in your own voice as "
        "Jarvis (never phrase this as being a different or lesser version of "
        "Jarvis, you ARE Jarvis, just answering through a backup connection "
        "right now), that this specific request needs a capability this "
        "connection doesn't have right now, and that it'll work once you're "
        "back on your main connection. If this sounds like it could be about "
        "updating your own code specifically, say so plainly instead of a "
        "generic capability answer -- that's handled by a separate, automatic "
        "system, so mention it should just work normally and suggest trying "
        "the exact phrase \"update yourself\"."
    )

    if context:
        prompt += "\n\nJARVIS CONTEXT:\n" + context

    return prompt


def ask_chat(
    prompt: str,
    *,
    spoken_name: str = "Sir",
    context: str = "",
) -> Dict[str, Any]:
    settings = load_settings()

    return _run(
        prompt,
        system_prompt=jarvis_system_prompt(
            spoken_name,
            context,
        ),
        effort=str(
            settings.get(
                "chat_effort",
                DEFAULT_EFFORT,
            )
        ),
        max_turns=1,
        tools="",
    )


def answer_grounded(
    question: str,
    web_context: str,
    *,
    memory_context: str = "",
    entity: str = "",
    public_ok: bool = False,
    memory_ok: bool = False,
    spoken_name: str = "Sir",
) -> Dict[str, Any]:
    settings = load_settings()

    system = (
        "You are Jarvis answering a user from research already gathered by "
        "Jarvis's search system. You have no web or computer tools in this call. "
        "PUBLIC WEB RESEARCH and PRIVATE JARVIS MEMORY are separate evidence "
        "classes. Never present private memory as public confirmation. "
        "Answer the question first. Prefer exact dates/numbers when evidence "
        "supports them. Distinguish confirmed facts from rumours or uncertainty. "
        "If relevant public evidence is missing, say so instead of guessing. "
        f"Address the user as {spoken_name} only when natural."
    )

    prompt = (
        f"QUESTION:\n{question}\n\n"
        f"PRIMARY ENTITY: {entity or '[not detected]'}\n"
        f"PUBLIC RELEVANCE PASSED: {bool(public_ok)}\n"
        f"PRIVATE MEMORY MATCHED ENTITY: {bool(memory_ok)}\n\n"
        f"PRIVATE JARVIS MEMORY / PROFILE:\n"
        f"{memory_context or '[none]'}\n\n"
        f"PUBLIC WEB RESEARCH:\n"
        f"{web_context or '[none]'}"
    )

    return _run(
        prompt,
        system_prompt=system,
        effort=str(
            settings.get(
                "research_effort",
                "high",
            )
        ),
        max_turns=1,
        tools="",
    )


def planner_model_call(
    system_prompt: str,
    user_prompt: str,
) -> str:
    settings = load_settings()

    result = _run(
        user_prompt,
        system_prompt=system_prompt,
        effort=str(
            settings.get(
                "planner_effort",
                "medium",
            )
        ),
        max_turns=1,
        tools="",
    )

    if result.get("ok"):
        return str(result.get("result", "") or "")

    raise RuntimeError(
        clean(result.get("error"))
        or "Claude planner failed."
    )


def diagnose_project(
    prompt: str = "",
) -> Dict[str, Any]:
    settings = load_settings()

    task = clean(prompt)

    if not task:
        task = (
            "Inspect the active Jarvis codebase starting from jarvis_app_v2.py. "
            "Diagnose the most likely current architectural or reliability "
            "problems. Read only. Do not edit, create, delete, move, rename or "
            "install anything. Give a concise diagnosis and recommended next "
            "actions."
        )

    system = (
        "You are Jarvis's read-only engineering diagnostician. "
        "This invocation is for inspection only. "
        "You may read/search project files, but you must not edit files, run "
        "destructive commands, install software, access credentials, expose "
        "secrets, change security settings, or make persistent system changes. "
        "Start from active imports and execution paths rather than assuming "
        "every old jarvis_*.py file is live."
    )

    return _run(
        task,
        system_prompt=system,
        effort=str(
            settings.get(
                "diagnostic_effort",
                "high",
            )
        ),
        timeout=max(
            240,
            int(
                settings.get(
                    "timeout_seconds",
                    DEFAULT_TIMEOUT,
                )
            ),
        ),
        max_turns=8,
        tools="Read,Glob,Grep",
        cwd=PROJECT_ROOT,
    )


def command_fast(
    command: str,
    spoken_name: str = "Sir",
) -> Optional[Dict[str, Any]]:
    low = clean(command).lower()

    if low in {
        "claude status",
        "claude code status",
        "is claude connected",
        "is claude working",
    }:
        info = status()

        if info["cli_found"]:
            state = (
                "enabled"
                if info["enabled"]
                else "disabled"
            )

            version = info.get("version") or "Claude Code"

            return {
                "mode": "chat",
                "reply": (
                    f"Claude is connected and {state}, {spoken_name}. "
                    f"{version}. Model route: {info['model']}."
                ),
                "steps": [],
            }

        return {
            "mode": "chat",
            "reply": (
                f"I can't find the Claude Code CLI, {spoken_name}. "
                "I'll keep using the local brain."
            ),
            "steps": [],
        }

    if low in {
        "claude mode on",
        "enable claude",
        "enable claude mode",
        "use claude",
    }:
        set_enabled(True)

        return {
            "mode": "chat",
            "reply": f"Claude routing is enabled, {spoken_name}.",
            "steps": [],
        }

    if low in {
        "claude mode off",
        "disable claude",
        "disable claude mode",
        "stop using claude",
    }:
        set_enabled(False)

        return {
            "mode": "chat",
            "reply": (
                f"Claude routing is disabled, {spoken_name}. "
                "I'll use the local brain."
            ),
            "steps": [],
        }

    if low in {
        "diagnose yourself",
        "claude diagnose yourself",
        "diagnose jarvis",
        "claude diagnose jarvis",
        "review yourself",
        "claude review yourself",
    }:
        result = diagnose_project()

        if result.get("ok"):
            return {
                "mode": "chat",
                "reply": str(
                    result.get("result", "")
                    or ""
                ),
                "steps": [],
            }

        return {
            "mode": "chat",
            "reply": (
                f"Claude couldn't complete the diagnostic, {spoken_name}. "
                f"{clean(result.get('error')) or 'I will keep using the existing systems.'}"
            ),
            "steps": [],
        }

    return None
