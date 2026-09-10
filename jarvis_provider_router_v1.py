"""
Jarvis Provider Router V1
===========================

Phase 1 of "Claude is no longer a required dependency": one real
provider registry that both of Jarvis's previously-separate AI code
paths route through, plus a genuine zero-setup local fallback.

Supersedes jarvis_brain_providers_v1.py (deleted, nothing else imported
it -- confirmed via repo-wide grep before removing it).

WHY THIS WAS NEEDED, CONFIRMED BY READING THE LIVE CODE FIRST: Jarvis
had two unrelated AI call paths, not one -- jarvis_claude_code_v1.py
(stateless, one `claude` CLI subprocess per call) and
jarvis_claude_brain_v2.py (a persistent warm session using the actual
claude_agent_sdk directly). Last session's jarvis_brain_providers_v1
only sat in front of the second one. This module is still deliberately
scoped the same way -- only the general-answer fallback path
(ask_active_brain, called from jarvis_app_v2.ask_ai_common_v2) is
provider-aware. Narrow internal judgment calls (clip curation, self-
diagnosis) stay on jarvis_claude_code_v1 directly, unchanged, on
purpose: they already degrade gracefully without Claude (the clipper
falls back to loudness-only ranking) and widening their scope isn't
needed to make Jarvis usable without a Claude subscription.

THE ACTUAL "CLAUDE NO LONGER REQUIRED" MECHANISM: confirmed live
(curl http://localhost:11434/api/tags on this machine) that
setup_environment.ps1 ALREADY installs Ollama and pulls qwen2.5vl:7b for
every single friend install, unconditionally, for JarvisVision -- and
confirmed that model's own capabilities list includes plain
"completion", not just vision. That means a genuinely free, zero-extra-
setup local brain already sits on disk for every existing and new
install; it was just never wired up as a selectable provider. So
get_active_provider() defaults to "claude" ONLY when Claude Code is
actually installed and found; otherwise it quietly defaults to "ollama"
instead of failing -- no wizard, no migration step, no action needed
from anyone. Existing Claude users see zero change (Claude is found,
stays default). This is Phase 1's whole answer to Section D/E/N from
the approved plan without needing the first-run wizard yet (that's
Phase 2).

Every non-Claude, non-Ollama adapter here (Gemini/Qwen-cloud/Codex/Kiro/
Minimax/OpenCode) is carried over unchanged from last session's
jarvis_brain_providers_v1 -- same caveat applies: built against each
provider's own current docs, not live-verified from this machine (no
account for any of them existed here). Ollama's adapter IS live-verified
-- confirmed against the real local server above.
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

import requests

import jarvis_claude_code_v1 as claude_v1

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

SETTINGS_DIR = MEMORY_ROOT / "settings"
SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
BRAIN_SETTINGS_PATH = SETTINGS_DIR / "brain_provider.json"

DEFAULT_TIMEOUT = 150
OLLAMA_BASE = "http://localhost:11434"
# The free local brain default. qwen2.5vl:7b used to be reused from
# JarvisVision's setup here, but live benchmarking on the dev machine put
# it at ~54 tok/s with an ~11s cold load -- the vision variant's multimodal
# overhead makes it the wrong tool for a text brain. qwen3:8b is the text
# model for that job: faster, better reasoning, and it still fits a 12GB
# VRAM card easily (5.2GB). JarvisVision keeps its own qwen2.5vl:7b pull
# for actual image work; the voice/text brain just doesn't ride on it.
OLLAMA_FALLBACK_MODEL = "qwen3:8b"
# The "download qwen locally" choice -- same text-first reasoning as the
# default above, single model to keep both fresh-install and existing
# installs on one answer instead of two different pulls.
OLLAMA_TEXT_MODEL = "qwen3:8b"
# Pin the brain model in VRAM so a cold conversation never eats an 11s
# model-reload before the first word comes out. Ollama evicts it only on
# Ollama restart or an explicit unload. JarvisVision's vision model still
# swaps in/out on demand; that path is infrequent and separate.
OLLAMA_KEEP_ALIVE = "24h"

PROVIDERS = {
    "claude": {
        "label": "Claude",
        "kind": "cloud",
        "cli_name": "claude",
        "install_cmd": None,
        "key_env": None,
        "free": False,
        "notes": "Jarvis's preferred brain. Needs Claude Pro or higher.",
    },
    "ollama": {
        "label": "Free Local AI",
        "kind": "local",
        "cli_name": None,
        "install_cmd": None,
        "key_env": None,
        "free": True,
        "notes": "Runs entirely on your own PC via Ollama -- already installed by Jarvis's own setup for JarvisVision, genuinely free, no account needed.",
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


def _default_provider():
    """Claude if it's actually installed (every existing user, unchanged
    experience); otherwise the free local model that's already sitting on
    disk from JarvisVision's own setup, rather than failing. This is the
    entire "Claude is no longer required" mechanism for brand-new users --
    no wizard needed for the default to already be usable."""
    if claude_v1.find_cli() is not None:
        return "claude"
    return "ollama"


def get_active_provider():
    """Claude is the only brain Jarvis chooses by default -- offering a
    switchable choice of providers caused real, confirmed confusion (the
    "backup line" tool-less fallback answering as though it were a lesser,
    different Jarvis; a flakier search pipeline on some code paths than
    Claude's own native WebSearch). The old stored "active" preference is
    deliberately ignored for that same reason. The ONE setting honored
    here is the explicit manual override to the backup brain, set by the
    "switch to backup brain" voice command and cleared by "switch back to
    claude" -- so a machine with no Claude CLI installed at all still
    doesn't get stuck with a fully dead assistant before Claude's set up."""
    data = _read_json(BRAIN_SETTINGS_PATH, {})
    override = str(data.get("override", "") or "").strip().lower()
    if override in PROVIDERS:
        return override
    return _default_provider()


def _manual_override_provider():
    """The provider the user explicitly switched to, or "" if they're on
    the default (auto-selected) brain. This is what distinguishes "I chose
    this on purpose" from "Jarvis picked this because Claude isn't there"
    -- ask_active_brain uses it to decide whether a failed backup deserves
    an emergency Claude fallback."""
    data = _read_json(BRAIN_SETTINGS_PATH, {})
    override = str(data.get("override", "") or "").strip().lower()
    return override if override in PROVIDERS else ""


def set_active_provider_override(provider_id):
    """Manual brain override, persisted next to the rest of the brain
    settings. Setting a real provider id pins Jarvis to it (used by the
    "switch to backup brain" command); anything else clears the override
    and drops back to the normal auto-selected default (Claude)."""
    data = _read_json(BRAIN_SETTINGS_PATH, {})
    if provider_id in PROVIDERS:
        data["override"] = provider_id
    else:
        data.pop("override", None)
    _write_json(BRAIN_SETTINGS_PATH, data)


def set_active_provider(provider_id):
    data = _read_json(BRAIN_SETTINGS_PATH, {})
    data["active"] = provider_id
    _write_json(BRAIN_SETTINGS_PATH, data)


def get_active_ollama_model():
    data = _read_json(BRAIN_SETTINGS_PATH, {})
    model = str(data.get("ollama_model", "") or "").strip()
    if model:
        return model
    return _ollama_auto_model() or OLLAMA_FALLBACK_MODEL


def set_active_ollama_model(model_name):
    data = _read_json(BRAIN_SETTINGS_PATH, {})
    data["ollama_model"] = model_name
    _write_json(BRAIN_SETTINGS_PATH, data)


EFFORT_LEVELS = ("low", "medium", "high")

# Real, verified model ids (from this environment's own system context),
# not guessed -- the one provider whose exact catalog was actually known
# at the time this was written. Every other provider deliberately does
# NOT get a hardcoded model list here: JarvisCode/settings show "default"
# for those instead of fabricating options, per the explicit "do not
# hard-code fake model options" requirement -- querying each provider's
# real catalog live is future work, not something to fake now.
CLAUDE_MODELS = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001", "claude-fable-5-1")


def list_models(provider_id):
    if provider_id == "claude":
        return list(CLAUDE_MODELS)
    if provider_id == "ollama":
        models = _ollama_list_models()
        return models if models else [OLLAMA_FALLBACK_MODEL]
    return ["default"]


def list_effort_levels(provider_id):
    # Only Claude Code's CLI has a confirmed --effort flag (checked its
    # own docs/flags before wiring this in). Other providers don't get a
    # fabricated list of levels they may not actually support.
    return list(EFFORT_LEVELS) if provider_id == "claude" else []


_PATH_REFRESHED = False


def _refresh_path_from_registry():
    """Reported as a real, still-live bug even after the first fix: "I
    have Codex installed, Jarvis still says I don't." The first fix only
    covered ONE specific gap (a fresh npm install landing in a hardcoded
    %APPDATA%\\npm that wasn't on Jarvis's PATH yet) -- not the general
    problem, which is that Jarvis is a long-running process whose PATH
    was snapshotted once at startup and never updated again, no matter
    what gets installed afterward, by npm or anything else, to any
    directory. The actual, general fix: read PATH fresh from the
    registry (both Machine and User scope -- exactly what
    setup_environment.ps1 already does after an install, and what a
    brand new terminal window gets automatically that this long-running
    process never does on its own) and prepend it to this process's own
    PATH. Runs once per process (cheap, but pointless to repeat on every
    single lookup) -- call reset via the module-level flag if a caller
    ever needs to force a second refresh."""
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
    # Prepend rather than replace -- never lose anything already working
    # (the venv's own Scripts dir in particular), just add what a fresh
    # process would see that this one doesn't yet.
    os.environ["PATH"] = fresh + (";" + current if current else "")


def _where(name):
    """Shells out to Windows' own `where`, which resolves PATH AND the
    "App Paths" registry key (HKLM/HKCU ...\\CurrentVersion\\App Paths) --
    a second, completely separate mechanism some installers register
    through instead of ever touching PATH at all, which shutil.which()
    never checks under any circumstances. This is what actually closes
    the gap for an installer neither of the other two strategies here
    were ever going to catch."""
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


def _npm_global_dirs():
    """The hardcoded %APPDATA%\\npm guess only holds for npm's own
    default prefix -- wrong for a custom prefix (.npmrc), nvm-managed
    Node installs, or a per-project/company override, all real setups
    that would make the earlier hardcoded-only fallback still fail
    exactly like the reported bug. Asking npm itself where its global
    packages actually live is the only way to get this right in
    general, so it's attempted first; the historical default is kept
    as a last-resort guess if npm can't be asked directly (e.g. npm
    itself isn't resolvable yet either)."""
    dirs = []
    npm_path = shutil.which("npm") or _where("npm")
    if npm_path:
        try:
            proc = subprocess.run(
                [npm_path, "root", "-g"], capture_output=True, text=True, timeout=8,
                shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            root = proc.stdout.strip()
            if proc.returncode == 0 and root:
                # `npm root -g` returns .../node_modules -- the actual
                # bin shims (the .cmd files) live one level up, in the
                # prefix dir itself, not inside node_modules.
                dirs.append(str(Path(root).parent))
        except Exception:
            pass

    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(str(Path(appdata) / "npm"))

    return dirs


def find_cli(name):
    """Layered, in order of cost: shutil.which() against a freshly
    registry-refreshed PATH (fixes the general staleness problem, not
    just one specific directory) -> Windows' own `where` (catches
    App-Paths-registered installs PATH-based lookups can never see at
    all) -> npm's actual configured global directory, asked live rather
    than guessed (catches a custom npm prefix/nvm setup) -> the old
    hardcoded %APPDATA%\\npm guess, kept only as the final fallback."""
    if not name:
        return None

    _refresh_path_from_registry()

    found = shutil.which(name)
    if found:
        return found

    found = _where(name)
    if found:
        return found

    for npm_dir in _npm_global_dirs():
        base = Path(npm_dir)
        for candidate in (base / f"{name}.cmd", base / f"{name}.exe", base / name):
            if candidate.exists():
                return str(candidate)

    return None


def _ollama_list_models():
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        r.raise_for_status()
        return [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
    except Exception:
        return []


def _ollama_auto_model():
    """Prefers whatever's already pulled over guessing -- a fresh Jarvis
    install already has OLLAMA_FALLBACK_MODEL from JarvisVision setup, but
    if the user later pulls something else and picks it, respect that."""
    models = _ollama_list_models()
    if not models:
        return None
    if OLLAMA_FALLBACK_MODEL in models:
        return OLLAMA_FALLBACK_MODEL
    return models[0]


def is_ready(provider_id):
    meta = PROVIDERS.get(provider_id)
    if not meta:
        return False, "unknown provider"

    if provider_id == "claude":
        return claude_v1.find_cli() is not None, "Claude Code CLI not found"

    if provider_id == "ollama":
        models = _ollama_list_models()
        if not models:
            return False, "Ollama isn't running or has no models pulled yet"
        return True, ""

    if not find_cli(meta["cli_name"]):
        return False, f"{meta['label']}'s CLI isn't installed yet"

    if meta["key_env"] and not os.environ.get(meta["key_env"], "").strip():
        return False, f"{meta['label']} needs an API key -- say \"change my {meta['key_env'].lower().replace('_', ' ')}\""

    return True, ""


def cli_missing(provider_id):
    """Genuinely real bug, confirmed live: every caller offering "install
    this?" was checking `not is_ready(provider_id)` -- but is_ready()
    returns False for TWO completely different reasons (CLI not found,
    OR CLI found fine but the API key isn't set yet), and every caller
    treated both the same way, offering to install a CLI that was
    already sitting right there on disk just because the key was
    missing. A user with Codex genuinely installed, just missing an
    OpenAI key, got told "isn't installed yet, install it now?" instead
    of the actually-correct "needs an API key" -- installing again would
    have done nothing, the real fix was always the key. This is the
    one specific question every install-prompt call site should
    actually be asking instead of reusing is_ready() for it."""
    meta = PROVIDERS.get(provider_id)
    if not meta:
        return False

    if provider_id == "claude":
        return claude_v1.find_cli() is None
    if provider_id == "ollama":
        return False  # nothing to "install" here in the CLI sense
    if not meta.get("cli_name"):
        return False

    return find_cli(meta["cli_name"]) is None


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

        # Confirmed live as the actual reported bug ("not actually
        # running the commands to download them"): on Windows, npm is
        # itself a .cmd batch file (npm.cmd), and subprocess.run(["npm",
        # ...], shell=False) raises FileNotFoundError -- CreateProcess
        # does not do the PATHEXT resolution a real shell would, so the
        # bare command name was never found at all. This was silently
        # caught by the except-Exception below and returned as an
        # unhelpful "Install failed: [WinError 2]..." -- meaning every
        # install_cmd starting with "npm" (every provider here except
        # Claude/Kiro) never actually ran, ever. Resolving the first
        # argument through shutil.which() first (same fix already
        # applied to find_cli() for the same root cause) gives
        # subprocess.run() the real, extension-qualified path.
        cmd = list(meta["install_cmd"])
        resolved = shutil.which(cmd[0])
        if resolved:
            cmd[0] = resolved

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            return False, f"Install failed: {e}"

        if proc.returncode != 0:
            return False, clean_stderr(proc.stderr) or "Install failed."

        if not find_cli(meta["cli_name"]):
            return False, f"{meta['label']} installed but its command isn't on PATH yet -- may need Jarvis restarted."

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


def _run_ollama(prompt, system_prompt, timeout):
    model = get_active_ollama_model()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    started = time.time()
    try:
        r = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={"model": model, "messages": messages, "stream": False,
                  "keep_alive": OLLAMA_KEEP_ALIVE,
                  # qwen3:8b is a "thinking" model -- confirmed live, without
                  # this it sometimes spends its entire reply writing out a
                  # long internal reasoning block and leaves "content" (the
                  # actual answer) completely empty, which read as "the
                  # backup brain is broken" and silently fell back to Claude
                  # every time it happened. think:false skips that reasoning
                  # step entirely: confirmed live, a real reply came back in
                  # ~0.27s instead of several seconds of hidden "thinking"
                  # text, and content is never empty anymore. This is also
                  # most of the actual "make qwen feel fast" fix -- the
                  # reasoning step, not raw model speed, was the slow part.
                  "think": False,
                  # num_gpu=-1 forces every layer onto the GPU instead of Ollama's
                  # own heuristic sometimes leaving some on CPU; num_predict caps
                  # generation length so a voice reply can't ramble past what
                  # actually needs speaking, which is most of the latency on a
                  # local model. num_ctx is left at Ollama's default since Jarvis's
                  # prompts here are short and a bigger context window only slows
                  # things down without adding anything.
                  "options": {"num_gpu": -1, "num_predict": 400}},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Ollama call failed ({model}): {e}", "result": ""}

    message = data.get("message") or {}
    result = str(message.get("content", "") or "").strip()
    if not result:
        # Last-ditch salvage: some models still put real text in "thinking"
        # even with think:false if the request omits it (older Ollama
        # servers ignore unknown fields silently) -- better to speak that
        # than to bounce to Claude over what's actually a working local reply.
        result = str(message.get("thinking", "") or "").strip()
    return {
        "ok": bool(result),
        "result": result,
        "error": "" if result else "Ollama returned an empty response",
        "elapsed": round(time.time() - started, 3),
    }


def _run_generic_cli(cli_path, extra_args, prompt, system_prompt, timeout):
    stdin_text = prompt
    if system_prompt:
        stdin_text = f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n\n[USER]\n{prompt}"

    started = time.time()
    try:
        proc = subprocess.run(
            [cli_path] + extra_args, input=stdin_text, text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=timeout, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timed out", "result": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "result": ""}

    data = _json_result(proc.stdout)
    result = _extract_text(data, proc.stdout)
    ok = bool(proc.returncode == 0 and result)
    return {
        "ok": ok,
        "result": result,
        "error": "" if ok else clean_stderr(proc.stderr),
        "elapsed": round(time.time() - started, 3),
    }


def _run_gemini_like(provider_id, prompt, system_prompt, timeout):
    """Live-tested for real against a real Gemini API key -- confirmed
    this was the actual reported bug ("Gemini doesn't seem to work"),
    never caught earlier because no real key existed on the dev machine
    until now. Gemini CLI (and Qwen Code, the fork sharing this same
    adapter) refuses to run headlessly in a directory it hasn't been
    interactively trusted in -- error text confirmed live: "Gemini CLI
    is not running in a trusted directory... use --skip-trust... for
    headless and automated environments." Jarvis only ever runs these
    headlessly, so every single call was failing on this before ever
    reaching the model at all. --skip-trust is documented by Gemini's
    own CLI specifically for this headless/automated case."""
    meta = PROVIDERS[provider_id]
    cli_path = find_cli(meta["cli_name"])
    if not cli_path:
        return {"ok": False, "error": f"{meta['label']} CLI not installed", "result": ""}
    return _run_generic_cli(cli_path, ["--output-format", "json", "--skip-trust"], prompt, system_prompt, timeout)


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
                [cli_path, "exec", "--json", "-o", out_file], input=stdin_text, text=True,
                encoding="utf-8", errors="replace", capture_output=True, timeout=timeout, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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
        return {"ok": ok, "result": result, "error": "" if ok else clean_stderr(proc.stderr)}


def _run_kiro(prompt, system_prompt, timeout):
    cli_path = find_cli("kiro")
    if not cli_path:
        return {"ok": False, "error": "Kiro CLI not installed", "result": ""}
    return _run_generic_cli(cli_path, ["chat", "--no-interactive", "--trust-tools"], prompt, system_prompt, timeout)


def _collect_opencode_text(stdout):
    """`opencode run --format json` emits one JSON event object per line:
    step_start / text / tool_use / step_finish / etc. The assistant's
    visible reply lives in the events where type == "text" and
    part.type == "text" (reasoning/meta text uses other shapes). Pull
    just those, in order, and join them -- the caller gets the reply,
    not a dump of raw NDJSON or the TUI's idle prompt text."""
    parts = []
    for line in str(stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except Exception:
            continue
        if evt.get("type") != "text":
            continue
        part = evt.get("part")
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        text = str(part.get("text", "") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def _run_opencode_like(prompt, system_prompt, timeout, model_flag=None):
    cli_path = find_cli("opencode")
    if not cli_path:
        return {"ok": False, "error": "OpenCode CLI not installed", "result": ""}

    # Live-verified on this machine: opencode's message parser chokes on
    # bracket-style "[SYSTEM INSTRUCTIONS]"/"[USER]" headers -- it answers
    # "I don't see a request here. What would you like help with?" and never
    # reaches the model. Weave the persona in as plain prose and put the
    # actual request last, plainly labelled, so the agent sees a real job
    # instead of a roleplay setup with no question.
    if system_prompt:
        stdin_text = (
            f"{system_prompt.strip()}\n\n"
            f"You are speaking directly to the user now. Their actual request "
            f"is at the end of this message -- answer it directly and stay in "
            f"your persona.\n\nUSER REQUEST:\n{prompt}"
        )
    else:
        stdin_text = prompt

    args = ["run", "--format", "json"]
    if model_flag:
        args += ["--model", model_flag]

    started = time.time()
    try:
        proc = subprocess.run(
            [cli_path] + args + [stdin_text], text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=timeout, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timed out", "result": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "result": ""}

    result = _collect_opencode_text(proc.stdout)
    ok = bool(proc.returncode == 0 and result)
    return {"ok": ok, "result": result, "error": "" if ok else clean_stderr(proc.stderr),
            "elapsed": round(time.time() - started, 3)}


def _ensure_minimax_opencode_config():
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


def run_provider(provider_id, prompt, *, system_prompt="", timeout=DEFAULT_TIMEOUT, effort="medium",
                  model=None, tools="", max_turns=1, cwd=None):
    """Same {ok, result, error} shape as jarvis_claude_code_v1._run() and
    jarvis_claude_brain_v2.ask_sync() so callers don't need to care which
    provider actually answered. model/tools/max_turns/cwd are honored for
    Claude (JarvisCode's Ask/Edit/Agent modes need real tool scoping and
    multi-turn runs, not just single-shot chat) and best-effort ignored
    elsewhere -- only Claude's adapter is a real tool-using agent today."""
    if provider_id == "claude":
        return claude_v1._run(
            prompt, system_prompt=system_prompt, model=model or "", effort=effort,
            timeout=timeout, max_turns=max_turns, tools=tools, cwd=cwd,
        )

    if provider_id == "ollama":
        return _run_ollama(prompt, system_prompt, timeout)

    if provider_id == "qwen":
        return _run_gemini_like("qwen", prompt, system_prompt, timeout)

    if provider_id == "gemini":
        return _run_gemini_like("gemini", prompt, system_prompt, timeout)

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


# Real, live exhaustion signals from Anthropic's API/SDK (rate_limit_error,
# 429, 529 overloaded, 402 billing_not_active, "out of credits", quota,
# etc.). Jarvis's voice brain runs on Claude by default, so when Claude is
# alive but genuinely out of quota or being rate-limited, ask_active_brain
# answers via the local qwen3:8b backup instead (Ollama, already pulled by
# setup_environment.ps1 for exactly this) -- and visibly says it did.
# Local, not another cloud provider: no separate account/API key for the
# user to manage, and it keeps answering even if the user's internet is
# the actual problem, not just Claude's quota. Anything else (timeout,
# network blip, SDK crash) deliberately does NOT switch: the user asked
# for a quota fallback, not a silent quality downgrade on every
# transient failure.
QUOTA_ERROR_RE = re.compile(
    r"(rate[-_ ]?limit|429|529|overload|quota|billing|402|payment|"
    r"out of credits?|insufficient|too many requests|limit exceeded)",
    re.IGNORECASE,
)


def ask_active_brain(prompt, *, spoken_name="Sir", timeout=DEFAULT_TIMEOUT, effort=None):
    """Drop-in replacement for the old direct claude_brain_v2.ask_sync()
    call site: if Claude is active (the default whenever it's actually
    installed), delegates straight to the existing warm-session brain,
    completely unchanged. Anything else -- including the "Claude isn't
    installed" default of "ollama" -- goes through this module's adapters.

    Claude-first with a local qwen3:8b safety net: if Claude answers, its
    reply comes back untouched. If Claude returns a quota/rate-limit
    exhaustion error (matched by QUOTA_ERROR_RE), the same prompt is
    re-run through Ollama's qwen3:8b model and that reply is returned
    with an in-band spoken note that Jarvis switched brains. If even the
    backup fails, Claude's original error is returned unchanged so
    callers see a real failure rather than a silent gap. All shapes stay
    {ok, result, error}, so no caller changes."""
    provider_id = get_active_provider()

    if provider_id == "claude":
        import jarvis_claude_brain_v2 as claude_brain_v2
        kwargs = {"timeout": timeout}
        if effort:
            kwargs["effort"] = effort
        result = claude_brain_v2.ask_sync(prompt, **kwargs)

        if not result.get("ok") and QUOTA_ERROR_RE.search(str(result.get("error", ""))):
            backup = run_provider(
                "ollama", prompt,
                system_prompt=claude_v1.jarvis_system_prompt(spoken_name),
                timeout=timeout, effort=effort or "medium",
            )
            if backup.get("ok") and backup.get("result"):
                return {
                    "ok": True,
                    "error": "",
                    "fallback_provider": "ollama",
                    "result": (
                        f"Just so you know, {spoken_name}, Claude is out of quota "
                        f"for the moment, so I answered this one on my local Qwen "
                        f"model instead -- everything else about me is the same. "
                        f"{str(backup['result']).strip()}"
                    ),
                }
            return result

        return result

    ready, reason = is_ready(provider_id)
    if not ready:
        return {"ok": False, "error": reason, "result": ""}

    system_prompt = claude_v1.jarvis_system_prompt(spoken_name)
    result = run_provider(provider_id, prompt, system_prompt=system_prompt, timeout=timeout, effort=effort or "medium")

    # A manually requested backup-brain switch failed mid-run -- never
    # leave Jarvis silent. Claude (when actually installed) is pulled in
    # as the emergency brain and the user is told the backup hiccuped,
    # instead of the explicit switch silently degrading into silence.
    if (not result.get("ok") and provider_id != "claude"
            and _manual_override_provider() == provider_id
            and claude_v1.find_cli() is not None):
        import jarvis_claude_brain_v2 as claude_brain_v2
        claude_kwargs = {"timeout": timeout}
        if effort:
            claude_kwargs["effort"] = effort
        claude_answer = claude_brain_v2.ask_sync(prompt, **claude_kwargs)
        if claude_answer.get("ok") and claude_answer.get("result"):
            claude_answer["fallback_provider"] = "claude"
            claude_answer["result"] = (
                f"Quick heads up, {spoken_name}: the backup brain had a "
                f"hiccup, so I've answered this one on Claude instead. "
                f"{str(claude_answer['result']).strip()}"
            )
            return claude_answer
        return result

    return result


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


# Brain-switch voice phrases. Deliberately exact-match, like the rest of
# the fast-path dispatcher -- "switch to opencode" could otherwise be
# misread as a desktop app-launch intent ("switch to ..." is an open-word
# in jarvis_desktop_v2), and the phrasings here intentionally don't
# collide with jarvis_claude_code_v1's own "claude mode on"/"use claude"
# handler set.
BRAIN_INFO_QUERIES = {
    "what model are you using",
    "what brain are you using",
    "list available models",
    "list models",
    "list brains",
    "show available brains",
}

# Real reported bug: "what model are you running on" (a completely
# natural phrasing) never matched the exact-string set above, so it fell
# through to the normal chat brain, which just answered as whatever
# model was actually live -- confusing when the active provider had
# switched but the user asked in slightly different words than the exact
# set covers. Loose, substring-based on purpose (unlike the switch
# commands above, "what model/brain ... running on/using" has no
# realistic collision with any other fast-path handler).
_BRAIN_INFO_RE = re.compile(
    r"\bwhat (model|brain) (are you|is jarvis|do you) (using|running on)\b"
)

BRAIN_SWITCH_BACKUP_QUERIES = {
    "switch to backup brain",
    "use backup brain",
    "use the backup brain",
    "switch to the backup brain",
    "switch to qwen",
    "use qwen",
    "run on qwen",
    "switch to the qwen brain",
    "switch to the local brain",
    "use the local brain",
}

BRAIN_RESTORE_CLAUDE_QUERIES = {
    "switch back to claude",
    "switch to claude",
    "switch to the claude brain",
    "go back to claude",
    "back to claude",
    "use the claude brain",
}


def is_brain_request(command):
    """Brain-intent gate for the fast-path dispatcher: informational
    "what are you running on" queries, the "switch to backup brain"
    command (pins Jarvis to the manual OpenCode override), and the
    "switch back to claude" restore. Manual switching was previously
    removed over the "backup answering as a lesser Jarvis" confusion --
    it's back now because that confusion is addressed head-on by having
    the switch announce itself in-band and stay underneath the same
    Jarvis persona either way. Extra words don't match (exact phrases
    only), same as every other fast-path handler."""
    c = _strip_wake(command)
    return (c in BRAIN_INFO_QUERIES or bool(_BRAIN_INFO_RE.search(c))
            or c in BRAIN_SWITCH_BACKUP_QUERIES or c in BRAIN_RESTORE_CLAUDE_QUERIES)


def brain_command_fast(command, spoken_name="Sir", app_module=None):
    c = _strip_wake(command)

    if not is_brain_request(command):
        return None

    if c in BRAIN_SWITCH_BACKUP_QUERIES:
        ready, reason = is_ready("ollama")
        if not ready:
            return _reply(f"I can't switch to the backup brain, {spoken_name} -- {reason}.")
        set_active_provider_override("ollama")
        return _reply(
            f"Switching to the backup brain, {spoken_name} -- I'm on my local "
            f"Qwen model now, running right here on your PC. Everything else "
            f"about me is the same; I'll stay here until you ask me to switch "
            f"back to Claude."
        )

    if c in BRAIN_RESTORE_CLAUDE_QUERIES:
        if _manual_override_provider() == "ollama":
            set_active_provider_override("")
            return _reply(
                f"Switching back to Claude, {spoken_name} -- my primary brain is restored."
            )
        if claude_v1.find_cli() is None:
            return _reply(
                f"I'm not on the backup brain right now, {spoken_name}, and I can't "
                f"switch to Claude -- the Claude CLI isn't installed on this machine."
            )
        return _reply(f"I'm already on Claude, {spoken_name} -- that's my primary brain.")

    if c in BRAIN_INFO_QUERIES or _BRAIN_INFO_RE.search(c):
        provider_id = get_active_provider()
        if provider_id == "ollama":
            return _reply(
                f"I'm running on my local Qwen model right now, {spoken_name} -- "
                f"the backup brain, right here on your PC. Say 'switch back to "
                f"claude' to put me on my primary brain again."
            )
        if provider_id == "claude":
            return _reply(
                f"I run on Claude, {spoken_name} -- that's my primary brain. Say "
                f"'switch to backup brain' if you ever want me to run on my "
                f"local Qwen model instead."
            )
        return _reply(
            f"I'm running on the free local brain, {spoken_name} "
            f"({PROVIDERS.get(provider_id, {}).get('label', provider_id)}), "
            f"since Claude isn't installed here."
        )

    return None
