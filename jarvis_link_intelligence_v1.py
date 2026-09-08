from __future__ import annotations

import json
import re
import webbrowser
from pathlib import Path
from urllib.parse import urlparse


PLATFORMS = {
    "twitch": {
        "aliases": {"twitch"},
        "direct": "https://www.twitch.tv/{handle}",
    },
    "kick": {
        "aliases": {"kick"},
        "direct": "https://kick.com/{handle}",
    },
    "instagram": {
        "aliases": {"instagram", "insta"},
        "direct": "https://www.instagram.com/{handle}/",
    },
    "tiktok": {
        "aliases": {"tiktok", "tik tok"},
        "direct": "https://www.tiktok.com/@{handle}",
    },
    "x": {
        "aliases": {"x", "twitter"},
        "direct": "https://x.com/{handle}",
    },
    "youtube": {
        "aliases": {"youtube", "you tube"},
        "direct": "https://www.youtube.com/@{handle}",
    },
    "github": {
        "aliases": {"github", "git hub"},
        "direct": "https://github.com/{handle}",
    },
}

ACTION_RE = re.compile(
    r"^\s*(?:jarvis\s+)?"
    r"(?:open|pull\s+up|bring\s+up|load|visit|go\s+to|take\s+me\s+to|show\s+me)\s+"
    r"(.+?)\s+(?:on|in)\s+"
    r"(twitch|kick|instagram|insta|tiktok|tik\s+tok|x|twitter|youtube|you\s+tube|github|git\s+hub)"
    r"\s*[.!?]*$",
    re.I,
)

URL_RE = re.compile(
    r"^\s*(?:jarvis\s+)?"
    r"(?:open|pull\s+up|bring\s+up|load|visit|go\s+to|take\s+me\s+to|show\s+me)\s+"
    r"(https?://\S+)\s*[.!?]*$",
    re.I,
)

HANDLE_RE = re.compile(r"^@?[A-Za-z0-9_.-]{2,40}$")

BLOCKED_PATHS = {
    "twitch": {
        "directory", "downloads", "jobs", "p", "search", "settings",
        "subscriptions", "videos",
    },
    "youtube": {
        "feed", "gaming", "premium", "results", "shorts", "watch",
    },
    "instagram": {
        "accounts", "direct", "explore", "p", "reel", "stories",
    },
    "tiktok": {"discover", "explore", "foryou", "login", "search"},
    "x": {"compose", "explore", "home", "i", "messages", "search", "settings"},
    "github": {"features", "marketplace", "orgs", "search", "settings", "topics"},
    "kick": {"categories", "category", "following", "search"},
}

_CACHE = None


def _root():
    preferred = Path(r"E:\JarvisMemory\links")
    fallback = Path(r"C:\AI-Agent\JarvisMemory\links")

    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except Exception:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


CACHE_FILE = _root() / "entity_links.json"


def _load_cache():
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _CACHE = data
        else:
            _CACHE = {}
    except Exception:
        _CACHE = {}

    return _CACHE


def _save_cache():
    try:
        CACHE_FILE.write_text(
            json.dumps(_load_cache(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _platform_name(value):
    value = re.sub(r"\s+", " ", str(value or "").lower().strip())

    for name, cfg in PLATFORMS.items():
        if value in cfg["aliases"]:
            return name

    return ""


def _handle(value):
    raw = str(value or "").strip()
    if not HANDLE_RE.fullmatch(raw):
        return ""

    return raw.lstrip("@").strip()


def _cache_key(platform, entity):
    return f"{platform}:{str(entity or '').lower().strip()}"


def canonical_direct_url(platform, entity):
    platform = _platform_name(platform) or str(platform or "").lower().strip()

    if platform not in PLATFORMS:
        return ""

    handle = _handle(entity)
    if not handle:
        return ""

    # Canonical profile slugs are normalised for direct navigation.
    handle = handle.lower()

    return PLATFORMS[platform]["direct"].format(handle=handle)


def _candidate_profile_url(platform, url):
    try:
        parsed = urlparse(str(url or ""))
        host = parsed.netloc.lower().removeprefix("www.")
        parts = [p for p in parsed.path.split("/") if p]
    except Exception:
        return ""

    if not parts:
        return ""

    if platform == "twitch":
        if not host.endswith("twitch.tv"):
            return ""
        if parts[0].lower() in BLOCKED_PATHS["twitch"]:
            return ""
        return f"https://www.twitch.tv/{parts[0]}"

    if platform == "kick":
        if not host.endswith("kick.com"):
            return ""
        if parts[0].lower() in BLOCKED_PATHS["kick"]:
            return ""
        return f"https://kick.com/{parts[0]}"

    if platform == "instagram":
        if not host.endswith("instagram.com"):
            return ""
        if parts[0].lower() in BLOCKED_PATHS["instagram"]:
            return ""
        return f"https://www.instagram.com/{parts[0]}/"

    if platform == "tiktok":
        if not host.endswith("tiktok.com"):
            return ""
        if not parts[0].startswith("@"):
            return ""
        return f"https://www.tiktok.com/{parts[0]}"

    if platform == "x":
        if not (host.endswith("x.com") or host.endswith("twitter.com")):
            return ""
        if parts[0].lower() in BLOCKED_PATHS["x"]:
            return ""
        return f"https://x.com/{parts[0]}"

    if platform == "github":
        if not host.endswith("github.com"):
            return ""
        if parts[0].lower() in BLOCKED_PATHS["github"]:
            return ""
        return f"https://github.com/{parts[0]}"

    if platform == "youtube":
        if not host.endswith("youtube.com"):
            return ""

        first = parts[0]

        if first.startswith("@"):
            return f"https://www.youtube.com/{first}"

        if first.lower() in {"channel", "c", "user"} and len(parts) >= 2:
            return f"https://www.youtube.com/{first}/{parts[1]}"

        return ""

    return ""


def resolve_profile_url(entity, platform, app_module, search_module=None):
    platform = _platform_name(platform)
    entity = str(entity or "").strip()

    if not platform or not entity:
        return "", "invalid"

    key = _cache_key(platform, entity)
    cached = str(_load_cache().get(key, "") or "").strip()

    if cached:
        return cached, "cache"

    direct = canonical_direct_url(platform, entity)

    # Handle-like identifiers are deterministic for these platforms.
    # This is the important MarkyADHD -> twitch.tv/markyadhd path.
    if direct:
        _load_cache()[key] = direct
        _save_cache()
        return direct, "direct"

    # Human/display names with spaces need silent profile resolution.
    query = f'site:{platform_domain(platform)} "{entity}"'

    try:
        data = app_module.web_research(query, max_results=8)
    except Exception:
        return "", "failed"

    candidates = []

    for item in list((data or {}).get("results", []) or []) + list(
        (data or {}).get("pages", []) or []
    ):
        if not isinstance(item, dict):
            continue

        url = (
            item.get("url")
            or item.get("link")
            or item.get("source_url")
            or item.get("href")
            or ""
        )

        profile = _candidate_profile_url(platform, url)
        if not profile:
            continue

        searchable = " ".join(
            str(item.get(k, "") or "")
            for k in ("title", "name", "snippet", "description", "text", "content")
        ).lower()

        target = re.sub(r"[^a-z0-9]+", "", entity.lower())
        hay = re.sub(r"[^a-z0-9]+", "", searchable.lower())

        score = 0
        if target and target in hay:
            score += 10

        profile_handle = profile.rstrip("/").split("/")[-1].lstrip("@")
        compact_handle = re.sub(r"[^a-z0-9]+", "", profile_handle.lower())

        if target and compact_handle == target:
            score += 15

        candidates.append((score, profile))

    if not candidates:
        return "", "not_found"

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_url = candidates[0]

    if best_score < 5:
        return "", "not_found"

    _load_cache()[key] = best_url
    _save_cache()

    return best_url, "resolved"


def platform_domain(platform):
    return {
        "twitch": "twitch.tv",
        "kick": "kick.com",
        "instagram": "instagram.com",
        "tiktok": "tiktok.com",
        "x": "x.com",
        "youtube": "youtube.com",
        "github": "github.com",
    }.get(_platform_name(platform), "")


def parse_link_command(command):
    text = str(command or "").strip()

    match = URL_RE.match(text)
    if match:
        return {
            "kind": "url",
            "url": match.group(1).rstrip(".,!?"),
        }

    match = ACTION_RE.match(text)
    if not match:
        return None

    entity = match.group(1).strip(" '\"")
    platform = _platform_name(match.group(2))

    if not entity or not platform:
        return None

    return {
        "kind": "platform_entity",
        "entity": entity,
        "platform": platform,
    }


def link_command_fast(command, spoken_name="Sir", app_module=None, search_module=None):
    parsed = parse_link_command(command)

    if not parsed:
        return None

    if parsed["kind"] == "url":
        url = parsed["url"]
        webbrowser.open(url)
        return {
            "mode": "chat",
            "reply": f"Opening it now, {spoken_name}.",
            "steps": [],
        }

    entity = parsed["entity"]
    platform = parsed["platform"]

    if app_module is None:
        return {
            "mode": "chat",
            "reply": f"I couldn't resolve that link, {spoken_name}.",
            "steps": [],
        }

    url, method = resolve_profile_url(
        entity,
        platform,
        app_module,
        search_module=search_module,
    )

    try:
        app_module.log(
            f"Link Intelligence: entity={entity!r}; platform={platform}; "
            f"method={method}; url={url or '-'}"
        )
    except Exception:
        pass

    if not url:
        return {
            "mode": "chat",
            "reply": (
                f"I couldn't confidently resolve the actual {platform.title()} "
                f"profile for {entity}, {spoken_name}, so I didn't open a random search page."
            ),
            "steps": [],
        }

    webbrowser.open(url)

    return {
        "mode": "chat",
        "reply": f"Opening {entity} on {platform.title()}, {spoken_name}.",
        "steps": [],
    }
