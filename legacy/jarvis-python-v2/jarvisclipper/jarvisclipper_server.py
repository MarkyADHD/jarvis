"""
JarvisClipper server -- local HTTP backend for the JarvisClipper app.

Same architecture as jarviscode_server.py and ai-visualizer/server.py
(stdlib http.server, no external web framework), same reason: this
project already proved that pattern relaunches safely as a plain script
where earlier pywebview/frozen-exe attempts hit a confirmed process-
spawn-loop bug (documented in jarvis_face_window.py). 127.0.0.1 only --
this reads/writes real files on disk and can trigger real yt-dlp/ffmpeg
work, no reason to expose it to the Tailscale mesh.

Shares jarvis_clipper_v1.py directly rather than reimplementing any of
its VOD-scanning/judging/cutting logic -- this server is just a UI on
top of the exact same pipeline the voice command "find clips from my
last stream" already uses.
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
REPO_ROOT = HERE.parent

sys.path.insert(0, str(REPO_ROOT))
import jarvis_clipper_v1 as clipper  # noqa: E402

PORT = 8796

# -------------------------------------------------------------------------
# Background jobs -- generation runs can take minutes, the UI polls
# /api/jobs/<id> for progress rather than holding one HTTP request open.
# -------------------------------------------------------------------------

_JOBS_LOCK = threading.Lock()
_JOBS = {}  # job_id -> {"status", "messages": [...], "clips": [...], "output_dir": str, "error": str}


def _start_generate_job(vod, max_clips, captions, vertical):
    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "status": "running",
            "messages": [],
            "clips": [],
            "output_dir": "",
            "error": "",
            "vod_title": vod.get("title", ""),
        }

    def progress(msg):
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job is not None:
                job["messages"].append(msg)

    def run():
        try:
            clips, output_dir = clipper.make_clips_from_vod(
                vod, max_clips=max_clips, progress_cb=progress,
                captions=captions, vertical=vertical,
            )
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job is not None:
                    job["status"] = "done"
                    job["clips"] = clips
                    job["output_dir"] = str(output_dir) if output_dir else ""
        except Exception as e:
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job is not None:
                    job["status"] = "failed"
                    job["error"] = str(e)

    threading.Thread(target=run, daemon=True).start()
    return job_id


# -------------------------------------------------------------------------
# Clip library -- scans CLIPS_ROOT for folders with a manifest.json
# -------------------------------------------------------------------------

def _list_clip_folders():
    root = clipper.CLIPS_ROOT
    if not root.exists():
        return []

    folders = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        if entry.name == "Live Clips" or not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            clips = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        folders.append({"folder": entry.name, "clips": clips})
    return folders


def _resolve_clip_file(folder, filename):
    """Path-traversal-safe resolution -- folder/filename both come
    straight from the URL, this is the one place that matters."""
    root = clipper.CLIPS_ROOT.resolve()
    target = (root / folder / filename).resolve()
    if root not in target.parents:
        return None
    return target if target.is_file() else None


_THUMB_CACHE_DIR = None


def _thumbnail_cache_dir():
    global _THUMB_CACHE_DIR
    if _THUMB_CACHE_DIR is None:
        _THUMB_CACHE_DIR = clipper.CLIPS_ROOT / ".thumbnails"
        _THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _THUMB_CACHE_DIR


def _get_or_make_thumbnail(video_path):
    cache_dir = _thumbnail_cache_dir()
    cache_key = re.sub(r"[^\w-]", "_", str(video_path.relative_to(clipper.CLIPS_ROOT)))
    thumb_path = cache_dir / f"{cache_key}.jpg"
    if thumb_path.exists():
        return thumb_path

    cmd = [
        "ffmpeg", "-y", "-ss", "1", "-i", str(video_path),
        "-frames:v", "1", "-vf", "scale=320:-1", "-q:v", "4",
        str(thumb_path),
    ]
    try:
        subprocess.run(
            cmd, capture_output=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    return thumb_path if thumb_path.exists() else None


# -------------------------------------------------------------------------
# HTTP handler
# -------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200, extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionError, BrokenPipeError):
            pass

    def _send_json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json", code)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _serve_file_with_range(self, path, ctype):
        """Real Range support, not just a flat file dump -- a plain
        200-with-the-whole-file response makes an HTML5 <video> unable
        to seek (the browser has no way to ask for just the bytes near
        the scrub position), which for a clip-review UI is the single
        most-used interaction. 206 Partial Content is what makes
        scrubbing/seeking actually work."""
        file_size = path.stat().st_size
        range_header = self.headers.get("Range")

        if not range_header:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 256)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except (ConnectionError, BrokenPipeError):
                pass
            return

        match = re.match(r"bytes=(\d*)-(\d*)", range_header)
        start_s, end_s = match.groups() if match else ("", "")
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        self.send_response(206)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(1024 * 256, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (ConnectionError, BrokenPipeError):
            pass

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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        try:
            if path == "/api/state":
                self._send_json({"ok": True, "clips_root": str(clipper.CLIPS_ROOT)})
                return

            if path == "/api/vods":
                limit = int((qs.get("limit") or ["10"])[0])
                vods = clipper.list_recent_vods(limit=limit)
                self._send_json({"vods": [
                    {"id": v.get("id", ""), "title": v.get("title", ""),
                     "duration": v.get("duration", ""), "created_at": v.get("created_at", ""),
                     "thumbnail_url": v.get("thumbnail_url", "")}
                    for v in vods
                ]})
                return

            if path == "/api/clips":
                self._send_json({"folders": _list_clip_folders()})
                return

            if path.startswith("/api/video/"):
                rel = path[len("/api/video/"):]
                folder, _, filename = rel.partition("/")
                target = _resolve_clip_file(folder, filename)
                if not target:
                    self._send(b"not found", "text/plain", 404)
                    return
                ctype = mimetypes.guess_type(str(target))[0] or "video/mp4"
                self._serve_file_with_range(target, ctype)
                return

            if path.startswith("/api/thumbnail/"):
                rel = path[len("/api/thumbnail/"):]
                folder, _, filename = rel.partition("/")
                target = _resolve_clip_file(folder, filename)
                if not target:
                    self._send(b"not found", "text/plain", 404)
                    return
                thumb = _get_or_make_thumbnail(target)
                if not thumb:
                    self._send(b"not found", "text/plain", 404)
                    return
                self._send(thumb.read_bytes(), "image/jpeg")
                return

            if path.startswith("/api/jobs/"):
                job_id = path[len("/api/jobs/"):]
                with _JOBS_LOCK:
                    job = _JOBS.get(job_id)
                    if not job:
                        self._send_json({"error": "unknown job"}, 404)
                        return
                    self._send_json(dict(job))
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
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/generate":
                body = self._read_json_body()
                vod_id = str(body.get("vod_id", "") or "").strip()
                vod_url = str(body.get("vod_url", "") or "").strip()
                max_clips = int(body.get("max_clips", clipper.DEFAULT_MAX_CLIPS) or clipper.DEFAULT_MAX_CLIPS)
                captions = bool(body.get("captions", True))
                vertical = bool(body.get("vertical", False))

                vod = None
                if vod_id:
                    vod = clipper.get_vod_by_id(vod_id)
                elif vod_url:
                    extracted = clipper.extract_vod_id(vod_url)
                    if extracted:
                        vod = clipper.get_vod_by_id(extracted)
                else:
                    recent = clipper.list_recent_vods(limit=1)
                    vod = recent[0] if recent else None

                if not vod:
                    self._send_json({"error": "Couldn't find that VOD."}, 400)
                    return

                job_id = _start_generate_job(vod, max_clips, captions, vertical)
                self._send_json({"job_id": job_id})
                return

            if path == "/api/open_folder":
                body = self._read_json_body()
                folder = str(body.get("folder", "") or "").strip()
                root = clipper.CLIPS_ROOT.resolve()
                target = (root / folder).resolve()
                if root not in target.parents and target != root:
                    self._send_json({"ok": False, "error": "invalid folder"}, 400)
                    return
                try:
                    os.startfile(str(target))
                    self._send_json({"ok": True})
                except Exception as e:
                    self._send_json({"ok": False, "error": str(e)}, 500)
                return

            if path == "/api/delete_clip":
                body = self._read_json_body()
                folder = str(body.get("folder", "") or "").strip()
                filename = str(body.get("file", "") or "").strip()
                target = _resolve_clip_file(folder, filename)
                if not target:
                    self._send_json({"ok": False, "error": "not found"}, 404)
                    return
                try:
                    target.unlink()
                    srt_path = target.with_suffix(".srt")
                    if srt_path.exists():
                        srt_path.unlink()
                    manifest_path = target.parent / "manifest.json"
                    if manifest_path.exists():
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest = [c for c in manifest if c.get("file") != filename]
                        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
                    self._send_json({"ok": True})
                except Exception as e:
                    self._send_json({"ok": False, "error": str(e)}, 500)
                return

            self._send_json({"error": "not found"}, 404)
        except ConnectionError:
            pass
        except Exception as e:
            try:
                self._send_json({"error": str(e)}, 500)
            except ConnectionError:
                pass


def run():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    run()
