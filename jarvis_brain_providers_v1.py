"""
Jarvis Brain Providers V1
===========================

Lets the user swap which AI actually answers Jarvis's general questions
and handles self-editing/diagnostic tasks -- "use gemini as my brain",
picked from the settings panel or by voice -- instead of being locked to
Claude. This exists specifically so someone without a Claude Pro
subscription can still run Jarvis on a free backend.

WHY THIS WAS SAFE TO ADD WITHOUT TOUCHING PC CONTROL/SPOTIFY/LIGHTS/ETC:
confirmed by reading the live code first -- none of Jarvis's device or
system control features are implemented as AI tool-calls. They're all
deterministic Python `*_command_fast()` routers (see jarvis_spotify_v2,
jarvis_keylight_v1, jarvis_clipper_v1, this project's own convention).
The AI "brain" is only ever used for two things: general conversational
answers (jarvis_claude_brain_v2.ask_sync, the fallback after every fast
router below has passed) and self-diagnosis/self-editing
(jarvis_claude_code_v1.diagnose_project and friends, Claude-only,
untouched by this module on purpose -- self-modification stays on the
model that's actually been tested doing it). Swapping the brain only
changes who answers plain questions; it never touches Jarvis's own
control surface.

HOW EACH PROVIDER WORKS: every one of these (Claude Code, Gemini CLI,
Qwen Code, Codex CLI, Kiro CLI, OpenCode) is its own standalone coding
agent with a documented headless mode: pipe a prompt in, get a finished
answer out, no different in shape from jarvis_claude_code_v1._run()'s
existing subprocess pattern -- confirmed against each project's own docs
before writing this. Minimax is the one exception: there is no
standalone Minimax agent CLI at all, only a raw pay-per-token API, so
its adapter routes through OpenCode configured with Minimax as the
underlying model -- OpenCode supplies the actual tool-use loop.

WHAT'S LIVE-VERIFIED VS. DOCS-ONLY: Claude's adapter is the existing,
already-proven jarvis_claude_code_v1 code, unchanged. Every other
adapter here was implemented against each project's own current
documentation but NOT run against a real account from this machine (no
Gemini/Qwen/OpenAI/Kiro/Minimax key was available at the time this was
written) -- confirmed live testing is still owed once a real key exists
for each, per this project's own "never hide failed tests" rule. Expect
to need to nudge exact CLI flag names once a real run surfaces a
mismatch; the fallback path (raw stdout if JSON parsing fails) exists
specifically to absorb small doc/reality drift without hard-failing.

"Download and run locally" (Qwen only, real weights via Ollama on the
user's own GPU) is a genuinely different, much heavier path than the
other providers' cloud CLIs -- only triggered by an explicit phrase
("download qwen locally"/"set up qwen locally"), never by just
switching the active provider, and it warns about size before pulling.
Only Qwen gets this: Claude/Gemini/Codex/Kiro are all closed-weight,
nothing to download; Minimax's own open weights are ~230B parameters
even quantized down, not a realistic local run for typical hardware, so
that combination is deliberately not offered here.

Examples:
    Jarvis switch to gemini
    Jarvis use claude as my brain
    Jarvis what model are you using
    Jarvis list available models
    Jarvis download qwen locally
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import jarvis_claude_code_v1 as claude_v1

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

SETTINGS_DIR = MEMORY_ROOT / "settings"
SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
BRAIN_SETTINGS_PATH = SETTINGS_DIR / "brain_provider.json"

DEFAULT_PROVIDER = "claude"
DEFAULT_TIMEOUT = 150
QWEN_LOCAL_MODEL = "qwen3-coder:30b"  # ~19GB pull, single-consumer-GPU class

# key_env is the jarvis_settings_v1 secret each provider's cloud API needs.
# install_cmd is None for Claude (already required for Jarvis itself) and
# for the two providers whose installers aren't plain npm packages.
PROVIDERS = {
    "claude": {
        "label": "Claude",
        "kind": "cloud",
        "cli_name": "claude",
        "install_cmd": None,
        "key_env": None,
        "free": False,
        "notes": "Jarvis's original brain. Needs Claude Pro or higher.",
    },
    "gemini": {
        "label": "Gemini",
        "kind": "cloud",
        "cli_name": "gemini",
        "install_cmd": ["npm", "install", "-g", "@google/gemini-cli"],
        "key_env": "GEMINI_API_KEY",
        "free": True,
        "notes": "Free tier, no card needed -- same key as JarvisThumbnails.",
    },
    "qwen": {
        "label": "Qwen (cloud)",
        "kind": "cloud",
        "cli_name": "qwen",
        "install_cmd": ["npm", "install", "-g", "@qwen-code/qwen-code@latest"],
        "key_env": "QWEN_API_KEY",
        "free": True,
        "notes": "Alibaba DashScope's free tier. Runs on their servers, not yours.",
    },
    "qwen_local": {
        "label": "Qwen (downloaded, runs on your own GPU)",
        "kind": "local",
        "cli_name": "qwen",
        "install_cmd": ["npm", "install", "-g", "@qwen-code/qwen-code@latest"],
        "key_env": None,
        "free": True,
        "notes": (
            f"Downloads real weights ({QWEN_LOCAL_MODEL}, ~19GB) via Ollama "
            "and runs entirely on your own GPU -- needs real VRAM (16GB+ for "
            "a usable model), not realistic on every machine."
        ),
    },
    "codex": {
        "label": "Codex (OpenAI)",
        "kind": "cloud",
        "cli_name": "codex",
        "install_cmd": ["npm", "install", "-g", "@openai/codex"],
        "key_env": "OPENAI_API_KEY",
        "free": False,
        "notes": "Needs your own paid OpenAI account -- no real free tier.",
    },
    "kiro": {
        "label": "Kiro (AWS)",
        "kind": "cloud",
        "cli_name": "kiro",
        "install_cmd": None,
        "key_env": "KIRO_API_KEY",
        "free": False,
        "notes": "Headless mode needs a paid Kiro Pro/Pro+/Power subscription.",
    },
    "minimax": {
        "label": "Minimax",
        "kind": "cloud",
        "cli_name": "opencode",
        "install_cmd": ["npm", "install", "-g", "opencode-ai"],
        "key_env": "MINIMAX_API_KEY",
        "free": False,
        "notes": (
            "No standalone Minimax agent exists -- runs through OpenCode "
            "configured against Minimax's API. Least battle-tested option here."
        ),
    },
    "opencode": {
        "label": "OpenCode",
        "kind": "cloud",
        "cli_name": "opencode",
        "install_cmd": ["npm", "install", "-g", "opencode-ai"],
        "key_env": None,
        "free": True,
        "notes": "Open-source, provider-agnostic -- defaults to Gemini's free tier.",
    },
}

SPOKEN_ALIASES = {
    "claude": "claude",
    "gemini": "gemini",
    "qwen": "qwen",
    "qwen cloud": "qwen",
    "qwen local": "qwen_local",
    "codex": "codex",
    "kiro": "kiro",
    "minimax": "minimax",
    "opencode": "opencode",
    "open code": "opencode",
}

_INSTALL_LOCK = threading.Lock()


def _read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_active_provider():
    data = _read_json(BRAIN_SETTINGS_PATH, {})
    provider = data.get("active", DEFAULT_PROVIDER)
    return provider if provider in PROVIDERS else DEFAULT_PROVIDER


def set_active_provider(provider_id):
    data = _read_json(BRAIN_SETTINGS_PATH, {})
    data["active"] = provider_id
    _write_json(BRAIN_SETTINGS_PATH, data)


def find_cli(name):
    return shutil.which(name)


def is_ready(provider_id):
    """CLI installed (or Claude, always considered installed) and, if it
    needs one, an API key configured. Doesn't check Ollama for qwen_local
    -- that's handled separately since it's a much heavier setup step."""
    meta = PROVIDERS.get(provider_id)
    if not meta:
        return False, "unknown provider"

    if provider_id == "claude":
        return claude_v1.find_cli() is not None, "Claude Code CLI not found"

    if not find_cli(meta["cli_name"]):
        return False, f"{meta['label']}'s CLI isn't installed yet"

    if meta["key_env"] and not os.environ.get(meta["key_env"], "").strip():
        return False, f"{meta['label']} needs an API key -- say \"change my {meta['key_env'].lower().replace('_', ' ')}\""

    return True, ""


def install_provider(provider_id, progress_cb=None):
    meta = PROVIDERS.get(provider_id)
    if not meta or not meta.get("install_cmd"):
        return False, "No automatic installer for this provider."

    def note(msg):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    with _INSTALL_LOCK:
        if find_cli(meta["cli_name"]):
            return True, ""

        note(f"Installing {meta['label']}'s CLI ({' '.join(meta['install_cmd'])})...")
        try:
            proc = subprocess.run(
                meta["install_cmd"],
                capture_output=True,
                text=True,
                timeout=300,
                shell=False,
            )
        except Exception as e:
            return False, f"Install failed: {e}"

        if proc.returncode != 0:
            return False, clean_stderr(proc.stderr) or "Install failed."

        if not find_cli(meta["cli_name"]):
            return False, (
                f"{meta['label']} installed but its command isn't on PATH yet "
                f"-- may need Jarvis restarted."
            )

        return True, ""


def clean_stderr(text):
    return str(text or "").strip()[:500]


def _json_result(text):
    text = str(text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    # Some of these CLIs print one JSON object per line (JSONL); the final
    # line is usually the completed result -- same defensive pattern
    # jarvis_claude_code_v1 already relies on for odd output shapes.
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except Exception:
            continue
    return {}


def _extract_text(data, raw_stdout):
    if isinstance(data, dict):
        for key in ("result", "response", "text", "message", "answer", "output"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                inner = value.get("text") or value.get("content")
                if isinstance(inner, str) and inner.strip():
                    return inner.strip()
    return str(raw_stdout or "").strip()


def _run_generic_cli(cli_path, extra_args, prompt, system_prompt, timeout):
    """Shared subprocess pattern for every CLI-based adapter: pipe the
    prompt (system prompt prepended, since not every one of these has a
    confirmed dedicated system-prompt flag) over stdin -- same Windows
    command-line-length workaround jarvis_claude_code_v1._run() already
    needed -- and read back JSON, falling back to raw stdout."""
    stdin_text = prompt
    if system_prompt:
        stdin_text = f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n\n[USER]\n{prompt}"

    started = time.time()
    try:
        proc = subprocess.run(
            [cli_path] + extra_args,
            input=stdin_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timed out", "result": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "result": ""}

    data = _json_result(proc.stdout)
    result = _extract_text(data, proc.stdout)
    ok = bool(proc.returncode == 0 and result)
    error = clean_stderr(proc.stderr) if not ok else ""

    return {
        "ok": ok,
        "result": result,
        "error": error,
        "elapsed": round(time.time() - started, 3),
    }


def _run_gemini_like(provider_id, prompt, system_prompt, timeout):
    meta = PROVIDERS[provider_id]
    cli_path = find_cli(meta["cli_name"])
    if not cli_path:
        return {"ok": False, "error": f"{meta['label']} CLI not installed", "result": ""}

    return _run_generic_cli(
        cli_path,
        ["--output-format", "json"],
        prompt,
        system_prompt,
        timeout,
    )


def _run_codex(prompt, system_prompt, timeout):
    cli_path = find_cli("codex")
    if not cli_path:
        return {"ok": False, "error": "Codex CLI not installed", "result": ""}

    with tempfile.TemporaryDirectory(prefix="jarvis_codex_") as tmp:
        out_file = str(Path(tmp) / "last_message.txt")
        stdin_text = prompt
        if system_prompt:
            stdin_text = f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n\n[USER]\n{prompt}"

        try:
            proc = subprocess.run(
                [cli_path, "exec", "--json", "-o", out_file],
                input=stdin_text,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timed out", "result": ""}
        except Exception as e:
            return {"ok": False, "error": str(e), "result": ""}

        result = ""
        try:
            result = Path(out_file).read_text(encoding="utf-8").strip()
        except Exception:
            pass

        if not result:
            result = _extract_text(_json_result(proc.stdout), proc.stdout)

        ok = bool(proc.returncode == 0 and result)
        return {
            "ok": ok,
            "result": result,
            "error": "" if ok else clean_stderr(proc.stderr),
        }


def _run_kiro(prompt, system_prompt, timeout):
    cli_path = find_cli("kiro")
    if not cli_path:
        return {"ok": False, "error": "Kiro CLI not installed", "result": ""}

    return _run_generic_cli(
        cli_path,
        ["chat", "--no-interactive", "--trust-tools"],
        prompt,
        system_prompt,
        timeout,
    )


def _run_opencode_like(prompt, system_prompt, timeout, model_flag=None):
    cli_path = find_cli("opencode")
    if not cli_path:
        return {"ok": False, "error": "OpenCode CLI not installed", "result": ""}

    stdin_text = prompt
    if system_prompt:
        stdin_text = f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n\n[USER]\n{prompt}"

    args = ["run"]
    if model_flag:
        args += ["--model", model_flag]

    started = time.time()
    try:
        proc = subprocess.run(
            [cli_path] + args + [stdin_text],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timed out", "result": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "result": ""}

    result = proc.stdout.strip()
    ok = bool(proc.returncode == 0 and result)
    return {
        "ok": ok,
        "result": result,
        "error": "" if ok else clean_stderr(proc.stderr),
    }


def _ensure_minimax_opencode_config():
    """Writes (or refreshes) an OpenCode custom-provider block pointing at
    Minimax's OpenAI-compatible endpoint, using MINIMAX_API_KEY. OpenCode's
    own config schema per its docs at time of writing; least-verified path
    in this module since it was never run against a real Minimax key."""
    config_dir = Path.home() / ".config" / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"

    data = _read_json(config_path, {})
    if not isinstance(data, dict):
        data = {}

    providers = data.setdefault("provider", {})
    providers["minimax"] = {
        "npm": "@ai-sdk/openai-compatible",
        "name": "Minimax",
        "options": {"baseURL": "https://api.minimax.io/v1"},
        "models": {"MiniMax-M2": {"name": "MiniMax-M2"}},
    }
    _write_json(config_path, data)

    creds_path = config_dir / "auth.json"
    creds = _read_json(creds_path, {})
    if not isinstance(creds, dict):
        creds = {}
    creds["minimax"] = {"apiKey": os.environ.get("MINIMAX_API_KEY", "")}
    _write_json(creds_path, creds)


def run_provider(provider_id, prompt, *, system_prompt="", timeout=DEFAULT_TIMEOUT, effort="medium"):
    """Same {ok, result, error} shape as jarvis_claude_code_v1._run() and
    jarvis_claude_brain_v2.ask_sync() so callers don't need to care which
    provider actually answered."""
    if provider_id == "claude":
        return claude_v1._run(prompt, system_prompt=system_prompt, effort=effort, timeout=timeout, max_turns=1, tools="")

    if provider_id in ("gemini", "qwen", "qwen_local"):
        return _run_gemini_like(provider_id if provider_id != "qwen_local" else "qwen", prompt, system_prompt, timeout)

    if provider_id == "codex":
        return _run_codex(prompt, system_prompt, timeout)

    if provider_id == "kiro":
        return _run_kiro(prompt, system_prompt, timeout)

    if provider_id == "opencode":
        return _run_opencode_like(prompt, system_prompt, timeout)

    if provider_id == "minimax":
        _ensure_minimax_opencode_config()
        return _run_opencode_like(prompt, system_prompt, timeout, model_flag="minimax/MiniMax-M2")

    return {"ok": False, "error": f"Unknown provider: {provider_id}", "result": ""}


def ask_active_brain(prompt, *, spoken_name="Sir", timeout=DEFAULT_TIMEOUT, effort=None):
    """Drop-in replacement call site for claude_brain_v2.ask_sync(): if
    Claude is the active provider (the default), delegates straight to the
    existing warm-session brain, completely unchanged. Anything else goes
    through this module's own per-call CLI adapters instead."""
    provider_id = get_active_provider()

    if provider_id == "claude":
        import jarvis_claude_brain_v2 as claude_brain_v2
        kwargs = {"timeout": timeout}
        if effort:
            kwargs["effort"] = effort
        return claude_brain_v2.ask_sync(prompt, **kwargs)

    ready, reason = is_ready(provider_id)
    if not ready:
        return {"ok": False, "error": reason, "result": ""}

    system_prompt = claude_v1.jarvis_system_prompt(spoken_name)
    return run_provider(provider_id, prompt, system_prompt=system_prompt, timeout=timeout, effort=effort or "medium")


# -------------------------------------------------------------------------
# Voice routing
# -------------------------------------------------------------------------

def _strip_wake(text):
    c = str(text or "").strip().lower()
    for wake in ("jarvis", "jervis", "jarviss"):
        if c == wake:
            return ""
        if c.startswith(wake + " "):
            return c[len(wake):].strip()
    return c


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def _match_provider_phrase(c):
    for phrase, provider_id in sorted(SPOKEN_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if phrase in c:
            return provider_id
    return None


def _run_switch_job(app_module, spoken_name, provider_id):
    meta = PROVIDERS[provider_id]
    ready, reason = is_ready(provider_id)

    if not ready and meta.get("install_cmd"):
        def note(msg):
            try:
                app_module.log(f"Brain switch: {msg}")
            except Exception:
                pass

        ok, error = install_provider(provider_id, progress_cb=note)
        if not ok:
            app_module.speak(f"I couldn't install {meta['label']}, {spoken_name}: {error}")
            return
        ready, reason = is_ready(provider_id)

    if not ready:
        app_module.speak(f"{meta['label']} isn't ready yet, {spoken_name}: {reason}")
        return

    set_active_provider(provider_id)
    app_module.speak(f"Switched to {meta['label']} as my brain, {spoken_name}.")


def _run_qwen_local_download_job(app_module, spoken_name):
    try:
        if not find_cli("ollama"):
            app_module.speak(
                f"I need Ollama installed first for local Qwen, {spoken_name} -- "
                f"grab it from ollama.com, then ask me again."
            )
            return

        app_module.log(f"Brain: pulling {QWEN_LOCAL_MODEL} via Ollama (~19GB)...")
        proc = subprocess.run(
            ["ollama", "pull", QWEN_LOCAL_MODEL],
            capture_output=True, text=True, timeout=3600, shell=False,
        )
        if proc.returncode != 0:
            app_module.speak(f"The Qwen download failed, {spoken_name}: {clean_stderr(proc.stderr)}")
            return

        if not find_cli("qwen"):
            install_provider("qwen_local")

        set_active_provider("qwen_local")
        app_module.speak(f"Qwen's downloaded and set as my brain, {spoken_name} -- running locally on your GPU now.")
    except Exception as e:
        try:
            app_module.speak(f"The local Qwen setup hit an error, {spoken_name}: {e}")
        except Exception:
            pass


def is_brain_request(command):
    c = _strip_wake(command)
    if any(p in c for p in ("as my brain", "switch to", "use claude", "use gemini", "use qwen", "use codex", "use kiro", "use minimax", "use opencode")):
        return True
    if c in {"what model are you using", "what brain are you using", "list available models", "list models", "list brains", "show available brains"}:
        return True
    if "download qwen locally" in c or "set up qwen locally" in c or "install qwen locally" in c:
        return True
    return False


def brain_command_fast(command, spoken_name="Sir", app_module=None):
    c = _strip_wake(command)

    if not is_brain_request(command):
        return None

    if "download qwen locally" in c or "set up qwen locally" in c or "install qwen locally" in c:
        threading.Thread(target=_run_qwen_local_download_job, args=(app_module, spoken_name), daemon=True).start()
        return _reply(
            f"Starting the local Qwen setup, {spoken_name} -- that's about a 19 gigabyte "
            f"download, could take a while depending on your connection."
        )

    if c in {"what model are you using", "what brain are you using"}:
        provider_id = get_active_provider()
        return _reply(f"I'm currently running on {PROVIDERS[provider_id]['label']}, {spoken_name}.")

    if c in {"list available models", "list models", "list brains", "show available brains"}:
        parts = [f"{m['label']} ({'free' if m['free'] else 'paid'})" for m in PROVIDERS.values()]
        return _reply(f"Available brains: {', '.join(parts)}, {spoken_name}.")

    provider_id = _match_provider_phrase(c)
    if provider_id:
        threading.Thread(target=_run_switch_job, args=(app_module, spoken_name, provider_id), daemon=True).start()
        meta = PROVIDERS[provider_id]
        return _reply(f"Switching to {meta['label']}, {spoken_name} -- one sec.")

    return None
