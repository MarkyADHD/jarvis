"""
JarvisCode server -- local HTTP backend for the JarvisCode desktop app.

Same architecture as ai-visualizer/server.py (stdlib http.server, no
external web framework) and the same reason: this whole project already
proved that pattern relaunches safely as a plain script where earlier
pywebview/frozen-exe attempts hit a confirmed process-spawn-loop bug
(documented in jarvis_face_window.py). 0.0.0.0 binding was deliberately
NOT copied from that file -- JarvisCode can read/write/run arbitrary
project files and shell commands, so unlike the read-only face HUD it
stays on 127.0.0.1 only, never exposed to the Tailscale mesh.

Shares Jarvis's own provider execution engine directly
(jarvis_provider_router_v1) rather than reimplementing any provider
logic -- the one duplicated-logic risk the approved plan explicitly
called out to avoid.
"""
import json
import mimetypes
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
REPO_ROOT = HERE.parent

sys.path.insert(0, str(REPO_ROOT))
import jarvis_provider_router_v1 as router  # noqa: E402
import jarvis_claude_code_v1 as claude_v1  # noqa: E402

PORT = 8795

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")
SESSION_PATH = MEMORY_ROOT / "settings" / "jarviscode_session.json"
SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)

# Deliberately excluded from the file tree -- huge/generated/irrelevant
# to "understand this project" the way node_modules or a venv is never
# something a developer wants an AI reading through by default.
TREE_EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build",
    ".idea", ".vscode", "target", ".next", ".cache", "bin", "obj",
}
TREE_MAX_ENTRIES = 2000

MODE_TOOLS = {
    "ask": "",
    "edit": "Read,Write,Edit,Glob,Grep",
    "agent": "Read,Write,Edit,Glob,Grep,Bash",
}
MODE_MAX_TURNS = {"ask": 1, "edit": 6, "agent": 20}


def _read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _session():
    data = _read_json(SESSION_PATH, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("provider", router.get_active_provider())
    data.setdefault("model", None)
    data.setdefault("effort", "medium")
    data.setdefault("project_root", "")
    return data


def _save_session(data):
    _write_json(SESSION_PATH, data)


def _safe_join(root, rel_path):
    """Refuses to resolve outside root -- the file tree/read endpoints
    take a client-supplied path, so this is the one thing standing
    between "browse this project" and an arbitrary-file-read bug."""
    root = Path(root).resolve()
    target = (root / str(rel_path or "").lstrip("/\\")).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path escapes project root")
    return target


def _list_tree(root):
    root = Path(root)
    entries = []
    count = 0

    def walk(dir_path, rel):
        nonlocal count
        try:
            children = sorted(
                dir_path.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except Exception:
            return
        for child in children:
            if count >= TREE_MAX_ENTRIES:
                return
            if child.name in TREE_EXCLUDE_DIRS:
                continue
            rel_child = f"{rel}/{child.name}" if rel else child.name
            if child.is_dir():
                entries.append({"path": rel_child, "type": "dir"})
                count += 1
                walk(child, rel_child)
            else:
                entries.append({"path": rel_child, "type": "file"})
                count += 1

    walk(root, "")
    return entries


def _is_git_repo(root):
    return (Path(root) / ".git").exists()


def _run_git(root, args, timeout=15):
    try:
        proc = subprocess.run(
            ["git"] + args, cwd=str(root), capture_output=True, text=True,
            timeout=timeout, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return 1, "", str(e)


def _build_project_context(root):
    if not root:
        return ""
    tree = _list_tree(root)[:300]
    lines = [f"Project root: {root}", "", "File tree (partial):"]
    for e in tree:
        lines.append(("  [dir] " if e["type"] == "dir" else "  ") + e["path"])
    return "\n".join(lines)


def _native_folder_picker():
    """A real Windows folder-picker dialog, run synchronously on the
    request-handling thread (ThreadingHTTPServer gives each request its
    own thread, so this doesn't block other requests). Tkinter, not a
    new dependency -- already used everywhere else in this project for
    exactly this kind of one-off native dialog (jarvis_settings_v1)."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Select a project folder for JarvisCode")
    root.destroy()
    return folder


JARVISCODE_SYSTEM_PROMPT = """You are JarvisCode, a coding-focused companion built on the same brain as Jarvis. You help with repositories, software projects, debugging, building applications, and game development. Be direct and concise. When editing/creating files, actually make the changes rather than just describing them, when the current mode allows it."""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code=200):
        self._send(json.dumps(obj).encode("utf-8"), "application/json", code)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        try:
            if path == "/api/state":
                sess = _session()
                self._send_json({
                    "providers": [
                        {"id": pid, "label": m["label"], "free": m["free"], "kind": m["kind"]}
                        for pid, m in router.PROVIDERS.items()
                    ],
                    "active_provider": sess["provider"],
                    "active_model": sess["model"],
                    "active_effort": sess["effort"],
                    "models": router.list_models(sess["provider"]),
                    "effort_levels": router.list_effort_levels(sess["provider"]),
                    "project_root": sess["project_root"],
                    "is_git_repo": _is_git_repo(sess["project_root"]) if sess["project_root"] else False,
                })
                return

            if path == "/api/models":
                provider_id = (qs.get("provider") or [""])[0]
                self._send_json({
                    "models": router.list_models(provider_id),
                    "effort_levels": router.list_effort_levels(provider_id),
                })
                return

            if path == "/api/tree":
                sess = _session()
                if not sess["project_root"]:
                    self._send_json({"entries": []})
                    return
                self._send_json({"entries": _list_tree(sess["project_root"])})
                return

            if path == "/api/file":
                sess = _session()
                rel = (qs.get("path") or [""])[0]
                target = _safe_join(sess["project_root"], rel)
                if not target.is_file():
                    self._send_json({"error": "not found"}, 404)
                    return
                try:
                    content = target.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
                    return
                self._send_json({"content": content})
                return

            if path == "/api/browse_folder":
                folder = _native_folder_picker()
                self._send_json({"path": folder or ""})
                return

            if path == "/api/diff":
                sess = _session()
                root = sess["project_root"]
                if not root or not _is_git_repo(root):
                    self._send_json({"available": False})
                    return
                code, out, err = _run_git(root, ["diff", "--stat"])
                code2, out2, err2 = _run_git(root, ["diff"])
                self._send_json({"available": True, "stat": out, "diff": out2})
                return

            self._static(path)
        except ConnectionError:
            pass
        except Exception as e:
            try:
                self._send_json({"error": str(e)}, 500)
            except ConnectionError:
                pass

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_json_body()

        try:
            if path == "/api/open_folder":
                folder = str(body.get("path", "")).strip()
                if not folder or not Path(folder).is_dir():
                    self._send_json({"ok": False, "error": "not a valid folder"}, 400)
                    return
                sess = _session()
                sess["project_root"] = str(Path(folder).resolve())
                _save_session(sess)
                self._send_json({"ok": True, "project_root": sess["project_root"]})
                return

            if path == "/api/set_provider":
                sess = _session()
                provider_id = str(body.get("provider", "")).strip()
                if provider_id not in router.PROVIDERS:
                    self._send_json({"ok": False, "error": "unknown provider"}, 400)
                    return
                sess["provider"] = provider_id
                sess["model"] = body.get("model") or None
                sess["effort"] = str(body.get("effort", "medium") or "medium")
                _save_session(sess)
                self._send_json({"ok": True})
                return

            if path == "/api/chat":
                self._handle_chat(body)
                return

            if path == "/api/rollback":
                sess = _session()
                root = sess["project_root"]
                if not root or not _is_git_repo(root):
                    self._send_json({"ok": False, "error": "not a git repo -- no rollback available"}, 400)
                    return
                target = str(body.get("path", "") or "").strip()
                if target:
                    code, out, err = _run_git(root, ["checkout", "--", target])
                else:
                    code, out, err = _run_git(root, ["checkout", "--", "."])
                self._send_json({"ok": code == 0, "error": err if code != 0 else ""})
                return

            self._send_json({"error": "not found"}, 404)
        except ConnectionError:
            pass
        except Exception as e:
            try:
                self._send_json({"error": str(e)}, 500)
            except ConnectionError:
                pass

    def _handle_chat(self, body):
        message = str(body.get("message", "") or "").strip()
        mode = str(body.get("mode", "ask") or "ask").strip()
        if mode not in MODE_TOOLS:
            mode = "ask"
        if not message:
            self._send_json({"ok": False, "error": "empty message"}, 400)
            return

        sess = _session()
        provider_id = sess["provider"]
        root = sess["project_root"] or None

        context = _build_project_context(root)
        prompt = message
        if context:
            prompt = f"[PROJECT CONTEXT]\n{context}\n\n[REQUEST]\n{message}"

        if provider_id == "claude":
            result = router.run_provider(
                "claude", prompt,
                system_prompt=JARVISCODE_SYSTEM_PROMPT,
                model=sess.get("model"),
                effort=sess.get("effort", "medium"),
                tools=MODE_TOOLS[mode],
                max_turns=MODE_MAX_TURNS[mode],
                cwd=Path(root) if root else None,
                timeout=600,
            )
        else:
            # Non-Claude providers don't have a confirmed tool-scoping
            # mechanism wired through this router yet -- honest about
            # that rather than silently running Ask-only logic and
            # calling it Agent mode.
            if mode != "ask":
                self._send_json({
                    "ok": False,
                    "error": f"{router.PROVIDERS[provider_id]['label']} only supports Ask mode in JarvisCode right now -- Edit/Agent mode needs Claude.",
                })
                return
            result = router.run_provider(
                provider_id, prompt, system_prompt=JARVISCODE_SYSTEM_PROMPT, timeout=120,
            )

        self._send_json({
            "ok": bool(result.get("ok")),
            "reply": result.get("result", ""),
            "error": result.get("error", ""),
        })

    def _static(self, path):
        if path == "/":
            path = "/index.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if target != STATIC_DIR and STATIC_DIR not in target.parents:
            self._send(b"not found", "text/plain", 404)
            return
        if not target.is_file():
            self._send(b"not found", "text/plain", 404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send(target.read_bytes(), ctype)


def run():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    run()
