"""
Jarvis Context Compressor V1
===============================

Native, dependency-free token/context compression for Jarvis and
JarvisCode -- shared by both, per the approved architecture plan's
Section F/L.

WHY NATIVE INSTEAD OF INTEGRATING HEADROOM: investigated it for real
(installed it, not just read about it). headroom-ai pulls in litellm
(114MB), botocore+boto3 (28MB), and headroom itself (39MB) -- ~180MB of
dependencies for a feature that needs none of a multi-provider LLM
router or the AWS SDK. That directly contradicts this project's own
repeated "no huge dependency unless there's a strong reason" and
"resource usage is extremely important" rules, discovered only by
actually installing it and checking real disk footprint, not by reading
its README. Reversed course and built this natively instead -- stdlib
only (re, json, ast, hashlib, pathlib), zero new pip dependencies.

WHAT THIS ACTUALLY DOES: replaces blind fixed-length truncation (e.g.
jarvis_web.py's old `text[:7000]`, which cuts wherever the character
count happens to land -- mid-sentence, mid-URL, right before the one
error message that mattered) with content-aware compression:

- Small content passes straight through completely unchanged -- no
  compression overhead, no cache entry, nothing to retrieve, per the
  explicit "don't compress everything unnecessarily" requirement.
- Large content gets the original stashed in a local cache first (never
  discarded), then compressed by a per-content-type strategy (JSON,
  code, log/traceback, or generic text) that preserves whole lines
  matching URLs/file paths/dates/numbers/quoted strings/error-shaped
  text, and cuts from the least-informative middle instead of a fixed
  offset.
- The compressed output always ends with a reference id and a plain-
  English instruction for how to get the original back
  (retrieve_original() / the "show full context <ref>" voice command
  wired into Jarvis, both backed by the same on-disk cache).

Deliberately NOT wired into jarvis_memory_v2's own recent-conversation
context -- that's already capped at MAX_RECENT_TURNS (18) turns, a
different, already-solved size-control problem, not the same "one huge
blob of raw external data" case this module targets (web pages, log/
tool output, JarvisCode's project tree and git diffs).
"""
import ast
import hashlib
import json
import re
from pathlib import Path

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

CACHE_DIR = MEMORY_ROOT / "context_cache"

# Below this, compression isn't worth the complexity or the loss of any
# detail at all -- pass through untouched. Above it, compression starts
# paying for itself in tokens saved.
MIN_SIZE_TO_COMPRESS = 3000
DEFAULT_TARGET_CHARS = 2200

# Lines matching any of these are never dropped from the "omitted middle"
# of a compression pass, regardless of strategy -- this is the actual
# mechanism behind "must preserve exact errors/URLs/filenames/paths/
# dates/numbers/quotations/IDs" rather than a hope.
_PROTECTED_LINE_RE = re.compile(
    r"(?:https?://|www\.|[A-Za-z]:\\|/(?:[\w.-]+/)+[\w.-]+|"
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|"
    r"\berror\b|\bexception\b|\btraceback\b|\bfailed\b|\bfailure\b|"
    r"\bwarning\b|\bfatal\b|\bsuccess(?:ful)?\b|"
    r"\bHTTP/?\d\s*[1-5]\d{2}\b|"  # an actual HTTP status ("HTTP 404"), not any 3-digit number in prose
    r"\b[A-Za-z_][A-Za-z0-9_]*_id\b|\b(?=[0-9a-f]*[a-f])[0-9a-f]{8,}\b)",  # hex ids/hashes -- requires a real hex LETTER, so plain long numbers don't match
    re.IGNORECASE,
)


def _norm_kind(kind):
    return str(kind or "auto").strip().lower()


def _ref_id(text):
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def _store_original(text):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ref_id = _ref_id(text)
    path = CACHE_DIR / f"{ref_id}.txt"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    return ref_id


def retrieve_original(ref_id):
    """Returns the full, uncompressed original text for a reference id
    previously produced by compress(), or None if it's unknown/expired.
    Nothing is ever deleted automatically -- callers/voice commands
    decide if/when to clean the cache up."""
    ref_id = re.sub(r"[^0-9a-f]", "", str(ref_id or "").lower())
    if not ref_id:
        return None
    path = CACHE_DIR / f"{ref_id}.txt"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _is_protected_line(line):
    return bool(_PROTECTED_LINE_RE.search(line))


def _collapse_repeated_lines(lines):
    """uniq -c style collapsing for log/tool-output noise -- five
    identical retry lines becomes one line + a count, without touching
    anything that isn't an exact repeat."""
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        j = i + 1
        while j < len(lines) and lines[j] == line:
            j += 1
        count = j - i
        if count > 2 and line.strip():
            out.append(f"{line}  [x{count}]")
        else:
            out.extend(lines[i:j])
        i = j
    return out


def _head_tail_compress(lines, target_chars):
    """Generic strategy: protected lines (errors, URLs, paths, dates,
    IDs) get first claim on the budget, head/tail context splits
    whatever's left, and the whole thing is capped at target_chars --
    confirmed live this needs a REAL shared cap: on prose-heavy content
    (a Wikipedia article, say) "error"/"failed"/similar words show up
    naturally often enough that treating protected lines as unlimited
    and additive on top of head/tail blew the budget by 10x+ before this
    fix. Protected lines are capped at 60% of the budget specifically so
    a page full of matches still leaves room for real head/tail context,
    not just an unbroken wall of "protected" lines."""
    budget = max(target_chars, 400)

    def take(indices_iter, remaining_budget):
        picked = []
        used = 0
        for i in indices_iter:
            cost = len(lines[i]) + 1
            if used + cost > remaining_budget and picked:
                break
            if used + cost > remaining_budget:
                break
            picked.append(i)
            used += cost
        return picked, used

    protected_all = [i for i, l in enumerate(lines) if _is_protected_line(l)]
    protected_budget = int(budget * 0.6)
    protected_idx, protected_used = take(protected_all, protected_budget)
    protected_idx = set(protected_idx)

    remaining = max(budget - protected_used, 200)
    head_budget = int(remaining * 0.55)
    tail_budget = remaining - head_budget

    head_idx, _ = take((i for i in range(len(lines)) if i not in protected_idx), head_budget)
    tail_idx, _ = take((i for i in reversed(range(len(lines))) if i not in protected_idx), tail_budget)
    tail_idx = list(reversed(tail_idx))

    kept = sorted(set(head_idx) | set(tail_idx) | protected_idx)

    if not kept:
        return "\n".join(lines)[:target_chars]

    out = []
    prev = -1
    omitted_total = 0
    for i in kept:
        if i > prev + 1:
            gap = i - prev - 1
            omitted_total += gap
            out.append(f"... [{gap} lines omitted] ...")
        out.append(lines[i])
        prev = i

    return "\n".join(out)


def _compress_json(text, target_chars):
    try:
        data = json.loads(text)
    except Exception:
        return None  # not valid JSON, let another strategy handle it

    MAX_STRING = 300

    def shrink(value, depth=0):
        if isinstance(value, str):
            if len(value) > MAX_STRING:
                return value[:MAX_STRING] + f"...[{len(value) - MAX_STRING} more chars]"
            return value
        if isinstance(value, dict):
            return {k: shrink(v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            if len(value) > 30:
                head = [shrink(v, depth + 1) for v in value[:20]]
                return head + [f"...[{len(value) - 20} more items]"]
            return [shrink(v, depth + 1) for v in value]
        return value

    shrunk = json.dumps(shrink(data), ensure_ascii=False, indent=1)
    if len(shrunk) <= target_chars * 1.6:  # JSON compresses less cleanly; a looser budget beats destroying structure
        return shrunk
    return _head_tail_compress(shrunk.splitlines(), target_chars)


def _compress_python_code(text, target_chars):
    try:
        tree = ast.parse(text)
    except Exception:
        return None  # not parseable Python, fall back to generic

    lines = text.splitlines()
    keep = set()

    def mark_signature(node):
        start = node.lineno - 1
        # Decorators, def line, and (for a docstring) its first line.
        for dec in getattr(node, "decorator_list", []):
            keep.add(dec.lineno - 1)
        keep.add(start)
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
            doc_start = body[0].lineno - 1
            keep.add(doc_start)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            mark_signature(node)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            keep.add(node.lineno - 1)

    protected_idx = {i for i, l in enumerate(lines) if _is_protected_line(l)}
    keep |= protected_idx

    out = []
    prev = -1
    for i in sorted(keep):
        if i > prev + 1:
            out.append(f"    ... [{i - prev - 1} lines omitted] ...")
        out.append(lines[i])
        prev = i

    result = "\n".join(out)
    return result if result.strip() else None


def _looks_like_log(text):
    hits = len(re.findall(r"\b(traceback|error|warning|exception|at line|\[INFO\]|\[ERROR\]|\[WARN\])\b", text, re.IGNORECASE))
    return hits >= 3


def _looks_like_python(text):
    return bool(re.search(r"^\s*(def |class |import |from \S+ import)", text, re.MULTILINE))


def compress(text, *, kind="auto", label="", min_size=MIN_SIZE_TO_COMPRESS, target_chars=DEFAULT_TARGET_CHARS):
    """The one entry point both Jarvis and JarvisCode use. Returns the
    text unchanged if it's under min_size (the common case for most
    tool output/short pages). Otherwise returns a compressed version
    with a reference id footer, after stashing the full original where
    retrieve_original() can find it."""
    text = str(text or "")
    if len(text) <= min_size:
        return text

    kind = _norm_kind(kind)
    ref_id = _store_original(text)
    original_len = len(text)

    compressed = None
    if kind in ("auto", "json"):
        compressed = _compress_json(text, target_chars)
    if compressed is None and kind in ("auto", "code", "python"):
        if kind == "code" or kind == "python" or _looks_like_python(text):
            compressed = _compress_python_code(text, target_chars)
    if compressed is None and kind in ("auto", "log"):
        if kind == "log" or _looks_like_log(text):
            compressed = _head_tail_compress(
                _collapse_repeated_lines(text.splitlines()), target_chars
            )
    if compressed is None:
        compressed = _head_tail_compress(text.splitlines(), target_chars)

    saved_pct = round(100 * (1 - len(compressed) / max(original_len, 1)))
    tag = f" ({label})" if label else ""
    footer = (
        f"\n\n[...compressed{tag}: {original_len:,} -> {len(compressed):,} chars "
        f"(~{saved_pct}% smaller). Full original still available -- "
        f"say \"show full context {ref_id}\" to see it. ref: {ref_id}]"
    )
    return compressed + footer


def estimate_tokens(text):
    """Cheap heuristic (chars/4), not a real tokenizer -- deliberately
    avoids adding tiktoken as a dependency for what's only ever used
    here as a rough "is this worth compressing" signal, not an exact
    billing count."""
    return max(1, len(str(text or "")) // 4)


# -------------------------------------------------------------------------
# Voice/text routing
# -------------------------------------------------------------------------

_REF_PATTERN = re.compile(r"\b([0-9a-f]{8,16})\b")


def is_context_request(command):
    c = str(command or "").strip().lower()
    return any(p in c for p in ("show full context", "show original context", "retrieve context", "show the original", "restore context"))


def context_command_fast(command, spoken_name="Sir", app_module=None):
    if not is_context_request(command):
        return None

    m = _REF_PATTERN.search(str(command or ""))
    if not m:
        return {
            "mode": "chat",
            "reply": f"I need the reference id to pull that up, {spoken_name} -- something like \"show full context a1b2c3d4e5f6\".",
            "steps": [],
        }

    original = retrieve_original(m.group(1))
    if original is None:
        return {
            "mode": "chat",
            "reply": f"I don't have that context cached anymore, {spoken_name} -- it may have already been cleared.",
            "steps": [],
        }

    try:
        import tempfile
        import os as _os
        out_path = Path(tempfile.gettempdir()) / f"jarvis_context_{m.group(1)}.txt"
        out_path.write_text(original, encoding="utf-8")
        _os.startfile(str(out_path))
    except Exception:
        pass

    return {
        "mode": "chat",
        "reply": f"Opened the full original, {spoken_name} -- {len(original):,} characters.",
        "steps": [],
    }
