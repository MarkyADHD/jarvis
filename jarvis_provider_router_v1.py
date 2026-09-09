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
# Same model setup_environment.ps1 already pulls for JarvisVision on
# every install -- reused here so "free local brain" needs nothing extra
# on any machine that's already run the normal installer.
OLLAMA_FALLBACK_MODEL = "qwen2.5vl:7b"
# A smaller, text-only pull offered specifically for "download qwen
# locally" -- not the vision model above, a real general-purpose local
# chat model, sized to actually be usable on a wider range of hardware
# than a 30B coding-specific model would be.
OLLAMA_TEXT_MODEL = "qwen2.5:7b"

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

SPOKEN_ALIASES = {
    "claude": "claude",
    "ollama": "ollama",
    "local ai": "ollama",
    "free local ai": "ollama",
    "gemini": "gemini",
    "qwen": "qwen",
    "qwen cloud": "qwen",
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
    data = _read_json(BRAIN_SETTINGS_PATH, {})
    provider = data.get("active")
    if provider in PROVIDERS:
        return provider
    return _default_provider()


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


def find_cli(name):
    return shutil.which(name) if name else None


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
                meta["install_cmd"], capture_output=True, text=True, timeout=300, shell=False,
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
            json={"model": model, "messages": messages, "stream": False},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Ollama call failed ({model}): {e}", "result": ""}

    result = str((data.get("message") or {}).get("content", "") or "").strip()
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
    meta = PROVIDERS[provider_id]
    cli_path = find_cli(meta["cli_name"])
    if not cli_path:
        return {"ok": False, "error": f"{meta['label']} CLI not installed", "result": ""}
    return _run_generic_cli(cli_path, ["--output-format", "json"], prompt, system_prompt, timeout)


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
            [cli_path] + args + [stdin_text], text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=timeout, shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timed out", "result": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "result": ""}

    result = proc.stdout.strip()
    ok = bool(proc.returncode == 0 and result)
    return {"ok": ok, "result": result, "error": "" if ok else clean_stderr(proc.stderr)}


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


def ask_active_brain(prompt, *, spoken_name="Sir", timeout=DEFAULT_TIMEOUT, effort=None):
    """Drop-in replacement for the old direct claude_brain_v2.ask_sync()
    call site: if Claude is active (the default whenever it's actually
    installed), delegates straight to the existing warm-session brain,
    completely unchanged. Anything else -- including the "Claude isn't
    installed" default of "ollama" -- goes through this module's adapters."""
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
        ollama_cli = find_cli("ollama")
        if not ollama_cli:
            app_module.speak(
                f"I need Ollama for local Qwen, {spoken_name}, and it's not on PATH -- "
                f"it should have been installed by Jarvis's own setup already, try restarting Jarvis first."
            )
            return

        app_module.log(f"Brain: pulling {OLLAMA_TEXT_MODEL} via Ollama...")
        proc = subprocess.run(
            [ollama_cli, "pull", OLLAMA_TEXT_MODEL], capture_output=True, text=True, timeout=3600, shell=False,
        )
        if proc.returncode != 0:
            app_module.speak(f"The Qwen download failed, {spoken_name}: {clean_stderr(proc.stderr)}")
            return

        set_active_ollama_model(OLLAMA_TEXT_MODEL)
        set_active_provider("ollama")
        app_module.speak(f"Qwen's downloaded and set as my brain, {spoken_name} -- running locally on your PC now.")
    except Exception as e:
        try:
            app_module.speak(f"The local Qwen setup hit an error, {spoken_name}: {e}")
        except Exception:
            pass


def is_brain_request(command):
    c = _strip_wake(command)
    if any(p in c for p in ("as my brain", "switch to", "use claude", "use gemini", "use qwen", "use codex", "use kiro", "use minimax", "use opencode", "use ollama", "use local ai", "use free local ai")):
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
        return _reply(f"Starting the local Qwen setup, {spoken_name} -- that's a real download, could take a few minutes.")

    if c in {"what model are you using", "what brain are you using"}:
        provider_id = get_active_provider()
        extra = f" ({get_active_ollama_model()})" if provider_id == "ollama" else ""
        return _reply(f"I'm currently running on {PROVIDERS[provider_id]['label']}{extra}, {spoken_name}.")

    if c in {"list available models", "list models", "list brains", "show available brains"}:
        parts = [f"{m['label']} ({'free' if m['free'] else 'paid'})" for m in PROVIDERS.values()]
        return _reply(f"Available brains: {', '.join(parts)}, {spoken_name}.")

    provider_id = _match_provider_phrase(c)
    if provider_id:
        threading.Thread(target=_run_switch_job, args=(app_module, spoken_name, provider_id), daemon=True).start()
        meta = PROVIDERS[provider_id]
        return _reply(f"Switching to {meta['label']}, {spoken_name} -- one sec.")

    return None
