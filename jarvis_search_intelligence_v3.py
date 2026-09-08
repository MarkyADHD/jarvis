"""
Jarvis Search Intelligence V3
=============================

Entity-aware web research and relevance filtering.

Goals:
- preserve exact entity/handle names
- reject irrelevant search results instead of treating result count as success
- retry weak entity searches with quoted/platform variants
- rank primary/authoritative sources
- dedupe result/page sets
- expose diagnostics to Jarvis
- let private Jarvis memory supplement, but never masquerade as, public web evidence
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "3.0.0"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "give", "has", "have", "how", "i",
    "in", "info", "information", "is", "it", "latest", "me", "news", "of",
    "on", "or", "please", "recent", "search", "tell", "that", "the", "this",
    "to", "was", "what", "when", "where", "which", "who", "why", "will",
    "with", "would", "you", "about", "current", "today", "update", "updates",
}

PRIMARY_DOMAINS = {
    "rockstargames.com": 4.0,
    "take2games.com": 4.0,
    "support.microsoft.com": 4.0,
    "microsoft.com": 3.5,
    "apple.com": 3.5,
    "support.spotify.com": 3.5,
    "spotify.com": 3.0,
    "github.com": 2.0,
}

PLATFORM_DOMAINS = {
    "youtube.com": 1.5,
    "twitch.tv": 1.5,
    "instagram.com": 1.5,
    "tiktok.com": 1.5,
    "x.com": 1.25,
    "twitter.com": 1.25,
}

ENTITY_PATTERNS = (
    r"^\s*who\s+is\s+(.+?)\s*[?!.]*$",
    r"^\s*who\s+are\s+(.+?)\s*[?!.]*$",
    r"^\s*tell\s+me\s+about\s+(.+?)\s*[?!.]*$",
    r"^\s*what\s+is\s+(.+?)\s*[?!.]*$",
    r"^\s*what\s+are\s+(.+?)\s*[?!.]*$",
    r"^\s*information\s+(?:on|about)\s+(.+?)\s*[?!.]*$",
    r"^\s*info\s+(?:on|about)\s+(.+?)\s*[?!.]*$",
)

RELEASE_PATTERNS = (
    r"^\s*when\s+does\s+(.+?)\s+release\s*[?!.]*$",
    r"^\s*what\s+date\s+does\s+(.+?)\s+release\s*[?!.]*$",
    r"^\s*when\s+is\s+(.+?)\s+releas(?:e|ing|ed)\s*[?!.]*$",
)

HANDLE_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_.-]{2,})")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9@._+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", norm(value))


def query_terms(query: Any) -> List[str]:
    terms = []
    for word in re.findall(r"[a-z0-9][a-z0-9_.+-]*", norm(query)):
        if len(word) < 2 or word in STOPWORDS:
            continue
        terms.append(word)
    return terms


def extract_primary_entity(query: Any) -> str:
    text = clean_text(query)

    handle = HANDLE_RE.search(text)
    if handle:
        return handle.group(1).strip()

    for pattern in ENTITY_PATTERNS:
        match = re.match(pattern, text, flags=re.I)
        if match:
            entity = match.group(1).strip(" '\".,?!")
            # Avoid treating generic concepts/questions as strict named entities.
            if entity and len(entity.split()) <= 8:
                return entity

    for pattern in RELEASE_PATTERNS:
        match = re.match(pattern, text, flags=re.I)
        if match:
            return match.group(1).strip(" '\".,?!")

    return ""


def looks_like_named_entity(entity: str) -> bool:
    if not entity:
        return False

    c = compact(entity)
    if len(c) < 3:
        return False

    # Handles/brand-like compact strings and digit-bearing product names are
    # especially suitable for strict relevance filtering.
    if "@" in entity or re.search(r"\d", entity):
        return True

    words = entity.split()
    if len(words) <= 4 and any(ch.isupper() for ch in entity):
        return True

    # Lowercase usernames passed through STT/app_normalise still need strict mode.
    if len(words) == 1 and 3 <= len(c) <= 32:
        return True

    return False


def query_variants(query: Any, max_variants: int = 6) -> List[str]:
    original = clean_text(query)
    entity = extract_primary_entity(original)

    values: List[str] = []

    def add(value: str) -> None:
        value = clean_text(value)
        if value and value.lower() not in {v.lower() for v in values}:
            values.append(value)

    add(original)

    if entity:
        bare = entity.lstrip("@").strip()
        add(f'"{bare}"')

        if len(bare.split()) <= 4:
            add(f'"{bare}" Twitch')
            add(f'"{bare}" YouTube')
            add(f'@{bare}')
            add(f'"{bare}" Instagram')

    return values[:max_variants]


def _domain(url: str) -> str:
    try:
        host = urlparse(str(url or "")).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def source_authority(url: str) -> float:
    host = _domain(url)

    for domain, score in PRIMARY_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return score

    for domain, score in PLATFORM_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return score

    return 0.0


def _field(item: Dict[str, Any], *names: str) -> str:
    for name in names:
        value = item.get(name)
        if value:
            return clean_text(value)
    return ""


def item_url(item: Dict[str, Any]) -> str:
    return _field(item, "url", "link", "source_url", "href")


def item_title(item: Dict[str, Any]) -> str:
    return _field(item, "title", "name", "heading")


def item_snippet(item: Dict[str, Any]) -> str:
    return _field(item, "snippet", "description", "summary", "excerpt")


def item_body(item: Dict[str, Any]) -> str:
    return _field(item, "text", "content", "body", "markdown", "page_text")


def _entity_presence_score(entity: str, text: str) -> float:
    if not entity or not text:
        return 0.0

    e_norm = norm(entity).lstrip("@")
    e_compact = compact(entity)
    t_norm = norm(text)
    t_compact = compact(text)

    score = 0.0

    if e_norm and e_norm in t_norm:
        score += 5.0

    if e_compact and e_compact in t_compact:
        score += 4.0

    entity_terms = query_terms(entity)
    if entity_terms:
        present = sum(1 for term in entity_terms if term in t_norm)
        coverage = present / max(1, len(entity_terms))
        score += coverage * 3.0

    # Fuzzy handle/name matching against words and URL-like tokens.
    if e_compact and len(e_compact) >= 4:
        candidates = re.findall(r"[a-z0-9_.-]{3,}", t_norm)
        best = 0.0
        for candidate in candidates[:100]:
            ratio = SequenceMatcher(None, e_compact, compact(candidate)).ratio()
            best = max(best, ratio)
        if best >= 0.92:
            score += 2.5
        elif best >= 0.82:
            score += 1.0

    return score


def score_item(
    item: Dict[str, Any],
    query: str,
    entity: str = "",
    inherited_score: float = 0.0,
) -> Tuple[float, Dict[str, float]]:
    title = item_title(item)
    snippet = item_snippet(item)
    body = item_body(item)
    url = item_url(item)

    title_score = _entity_presence_score(entity, title)
    snippet_score = _entity_presence_score(entity, snippet)
    body_score = _entity_presence_score(entity, body)
    url_score = _entity_presence_score(entity, url)

    terms = query_terms(query)
    searchable = norm(" ".join((title, snippet, body, url)))
    overlap = sum(1 for term in terms if term in searchable)
    overlap_score = min(3.0, overlap * 0.75)

    authority = source_authority(url)

    # Entity presence dominates authority. An authoritative YouTube page about
    # parental controls must not be accepted for "MarkyADHD".
    score = (
        title_score * 1.35
        + snippet_score
        + body_score * 0.85
        + url_score * 1.15
        + overlap_score
        + authority
        + max(0.0, inherited_score * 0.65)
    )

    return score, {
        "title": round(title_score, 2),
        "snippet": round(snippet_score, 2),
        "body": round(body_score, 2),
        "url": round(url_score, 2),
        "overlap": round(overlap_score, 2),
        "authority": round(authority, 2),
        "inherited": round(inherited_score, 2),
    }


def _result_key(item: Dict[str, Any]) -> str:
    url = item_url(item)
    if url:
        return norm(url)
    return norm(item_title(item) + " " + item_snippet(item))[:500]


def _page_key(item: Dict[str, Any]) -> str:
    url = item_url(item)
    if url:
        return norm(url)
    return norm(item_title(item) + " " + item_body(item)[:300])[:500]


def _threshold(entity: str, strict_entity: bool, item_kind: str) -> float:
    if strict_entity:
        return 6.0 if item_kind == "result" else 5.0
    if entity:
        return 3.0
    return 0.75


def filter_web_data(
    web_data: Dict[str, Any],
    query: str,
    entity: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    web_data = web_data if isinstance(web_data, dict) else {}
    results = list(web_data.get("results", []) or [])
    pages = list(web_data.get("pages", []) or [])

    strict_entity = looks_like_named_entity(entity)

    accepted_results = []
    rejected_results = []
    result_scores_by_url: Dict[str, float] = {}

    for item in results:
        if not isinstance(item, dict):
            continue

        score, parts = score_item(item, query, entity)
        enriched = dict(item)
        enriched["_jarvis_relevance_score"] = round(score, 2)
        enriched["_jarvis_relevance_parts"] = parts

        threshold = _threshold(entity, strict_entity, "result")
        if score >= threshold:
            accepted_results.append(enriched)
            url = item_url(item)
            if url:
                result_scores_by_url[norm(url)] = score
        else:
            rejected_results.append(enriched)

    accepted_pages = []
    rejected_pages = []

    for item in pages:
        if not isinstance(item, dict):
            continue

        inherited = 0.0
        url = item_url(item)
        if url:
            inherited = result_scores_by_url.get(norm(url), 0.0)

        score, parts = score_item(item, query, entity, inherited_score=inherited)
        enriched = dict(item)
        enriched["_jarvis_relevance_score"] = round(score, 2)
        enriched["_jarvis_relevance_parts"] = parts

        threshold = _threshold(entity, strict_entity, "page")
        if score >= threshold:
            accepted_pages.append(enriched)
        else:
            rejected_pages.append(enriched)

    accepted_results.sort(
        key=lambda x: float(x.get("_jarvis_relevance_score", 0.0)),
        reverse=True,
    )
    accepted_pages.sort(
        key=lambda x: float(x.get("_jarvis_relevance_score", 0.0)),
        reverse=True,
    )

    filtered = dict(web_data)
    filtered["results"] = accepted_results
    filtered["pages"] = accepted_pages

    top_scores = []
    for item in (accepted_results + accepted_pages)[:8]:
        top_scores.append({
            "title": item_title(item)[:100],
            "url": item_url(item)[:220],
            "score": item.get("_jarvis_relevance_score", 0.0),
        })

    diag = {
        "entity": entity,
        "strict_entity": strict_entity,
        "input_results": len(results),
        "input_pages": len(pages),
        "relevant_results": len(accepted_results),
        "relevant_pages": len(accepted_pages),
        "discarded_results": len(rejected_results),
        "discarded_pages": len(rejected_pages),
        "top_scores": top_scores,
    }

    return filtered, diag


def _merge_unique(existing: List[Dict[str, Any]], new_items: Iterable[Dict[str, Any]], key_fn) -> None:
    seen = {key_fn(item) for item in existing if key_fn(item)}
    for item in new_items:
        if not isinstance(item, dict):
            continue
        key = key_fn(item)
        if key and key in seen:
            continue
        existing.append(item)
        if key:
            seen.add(key)


def research_with_relevance(
    query: str,
    research_func,
    max_results: int = 8,
    max_attempts: int = 4,
) -> Dict[str, Any]:
    entity = extract_primary_entity(query)
    variants = query_variants(query)
    strict_entity = looks_like_named_entity(entity)

    merged_results: List[Dict[str, Any]] = []
    merged_pages: List[Dict[str, Any]] = []

    discarded_results = 0
    discarded_pages = 0
    attempts = []
    relevant_seen = 0

    for index, variant in enumerate(variants[:max_attempts], start=1):
        data = research_func(variant, max_results=max_results)
        filtered, diag = filter_web_data(data, query=query, entity=entity)

        _merge_unique(
            merged_results,
            filtered.get("results", []) or [],
            _result_key,
        )
        _merge_unique(
            merged_pages,
            filtered.get("pages", []) or [],
            _page_key,
        )

        discarded_results += int(diag.get("discarded_results", 0))
        discarded_pages += int(diag.get("discarded_pages", 0))

        attempts.append({
            "query": variant,
            "relevant_results": diag.get("relevant_results", 0),
            "relevant_pages": diag.get("relevant_pages", 0),
            "discarded_results": diag.get("discarded_results", 0),
            "discarded_pages": diag.get("discarded_pages", 0),
            "top_scores": diag.get("top_scores", [])[:3],
        })

        relevant_seen = len(merged_results) + len(merged_pages)

        # Generic searches should stay fast. Strict entity searches need actual
        # evidence before they stop.
        if not strict_entity and relevant_seen > 0:
            break

        if strict_entity:
            strong = [
                x for x in (merged_results + merged_pages)
                if float(x.get("_jarvis_relevance_score", 0.0)) >= 9.0
            ]
            if len(strong) >= 1 and relevant_seen >= 2:
                break

    merged_results.sort(
        key=lambda x: float(x.get("_jarvis_relevance_score", 0.0)),
        reverse=True,
    )
    merged_pages.sort(
        key=lambda x: float(x.get("_jarvis_relevance_score", 0.0)),
        reverse=True,
    )

    public_ok = bool(merged_results or merged_pages)

    diagnostics = {
        "version": VERSION,
        "entity": entity,
        "strict_entity": strict_entity,
        "query_variants": variants[:max_attempts],
        "attempts": attempts,
        "retry_count": max(0, len(attempts) - 1),
        "relevant_results": len(merged_results),
        "relevant_pages": len(merged_pages),
        "discarded_results": discarded_results,
        "discarded_pages": discarded_pages,
        "public_relevance_ok": public_ok,
        "top_scores": [
            {
                "title": item_title(item)[:100],
                "url": item_url(item)[:220],
                "score": item.get("_jarvis_relevance_score", 0.0),
            }
            for item in (merged_results + merged_pages)[:6]
        ],
    }

    return {
        "query": query,
        "entity": entity,
        "web_data": {
            "results": merged_results,
            "pages": merged_pages,
        },
        "diagnostics": diagnostics,
    }


def context_mentions_entity(context: Any, entity: str) -> bool:
    if not entity:
        return False

    ctx = compact(context)
    ent = compact(entity)

    if not ent or not ctx:
        return False

    if ent in ctx:
        return True

    terms = query_terms(entity)
    if not terms:
        return False

    normal = norm(context)
    return all(term in normal for term in terms)


def diagnostics_line(diag: Dict[str, Any]) -> str:
    diag = diag if isinstance(diag, dict) else {}
    entity = diag.get("entity") or "-"
    return (
        f"Search Intelligence V3: entity={entity!r}; "
        f"relevant results={diag.get('relevant_results', 0)}; "
        f"relevant pages={diag.get('relevant_pages', 0)}; "
        f"discarded={diag.get('discarded_results', 0) + diag.get('discarded_pages', 0)}; "
        f"retries={diag.get('retry_count', 0)}"
    )
