from __future__ import annotations

import concurrent.futures
import ipaddress
import re
import socket
from datetime import datetime
from urllib.parse import urlparse

import requests

import jarvis_search_intelligence_v3 as v3


VERSION = "4.0.0"

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)

DATE_RE = re.compile(
    rf"\b(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,\s*|\s+)\d{{4}}\b",
    re.I,
)

PRICE_RE = re.compile(
    r"(?:£|\$|€)\s?\d+(?:,\d{3})*(?:\.\d{1,2})?"
)

VERSION_RE = re.compile(
    r"\b(?:version|v)\s*\d+(?:\.\d+){1,4}\b",
    re.I,
)

RELEASE_WORDS = {
    "release", "releases", "released", "launch", "launches",
    "launching", "coming", "available", "ships",
}

PUBLICATION_WORDS = {
    "published", "posted", "updated", "newswire", "article",
}


def expected_answer_type(query):
    q = v3.norm(query)

    if re.search(r"\b(when|what date|release date|launch date)\b", q):
        return "date"

    if re.search(r"\b(how much|price|cost)\b", q):
        return "price"

    if re.search(r"\b(latest version|current version|what version)\b", q):
        return "version"

    if re.search(r"\b(schedule|fixtures?|when is|what time)\b", q):
        return "schedule"

    if re.search(r"\b(latest|news|recent|today|currently|current)\b", q):
        return "latest"

    return "generic"


def smart_query_variants(query, max_variants=6):
    original = v3.clean_text(query)
    entity = v3.extract_primary_entity(original)
    answer_type = expected_answer_type(original)
    year = datetime.now().year

    values = []

    def add(value):
        value = v3.clean_text(value)
        if value and value.lower() not in {x.lower() for x in values}:
            values.append(value)

    add(original)

    if answer_type == "date":
        if entity:
            add(f'"{entity}" exact release date official')
            add(f'"{entity}" release date official')
            add(f'"{entity}" launch date')
        else:
            add(original + " exact date official")
            add(original + " official")

    elif answer_type == "price":
        if entity:
            add(f'"{entity}" current price official')
            add(f'"{entity}" price {year}')
        else:
            add(original + " official price")

    elif answer_type == "version":
        if entity:
            add(f'"{entity}" latest version official')
            add(f'"{entity}" current version {year}')
        else:
            add(original + " official latest version")

    elif answer_type == "latest":
        add(original + f" {year}")
        add(original + " official")

        if entity:
            add(f'"{entity}" latest official')
            add(f'"{entity}" news {year}')

    else:
        for variant in v3.query_variants(original, max_variants=max_variants):
            add(variant)

    return values[:max_variants]


def _safe_public_url(url):
    try:
        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"}:
            return False

        host = parsed.hostname
        if not host:
            return False

        low = host.lower()

        if low in {"localhost"} or low.endswith(".local"):
            return False

        try:
            ip = ipaddress.ip_address(host)
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
            )
        except ValueError:
            pass

        try:
            infos = socket.getaddrinfo(host, None)
            for info in infos[:4]:
                raw = info[4][0]
                ip = ipaddress.ip_address(raw)
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_reserved
                ):
                    return False
        except Exception:
            pass

        return True

    except Exception:
        return False


def _strip_html(html):
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    except Exception:
        text = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()


def ddgs_research(query, max_results=8):
    try:
        from ddgs import DDGS
    except Exception:
        return {"results": [], "pages": [], "provider": "ddgs_unavailable"}

    try:
        rows = list(
            DDGS().text(
                query,
                max_results=max_results,
            )
        )
    except Exception:
        return {"results": [], "pages": [], "provider": "ddgs_failed"}

    results = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        url = str(row.get("href") or row.get("url") or "")
        if not _safe_public_url(url):
            continue

        results.append({
            "title": str(row.get("title") or ""),
            "snippet": str(row.get("body") or row.get("snippet") or ""),
            "link": url,
            "_provider": "ddgs",
        })

    pages = []

    def fetch(item):
        url = item.get("link", "")
        try:
            r = requests.get(
                url,
                timeout=10,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                    )
                },
            )
            r.raise_for_status()

            ctype = str(r.headers.get("content-type", "")).lower()
            if "text/html" not in ctype:
                return None

            text = _strip_html(r.text[:750000])[:35000]

            if not text:
                return None

            return {
                "url": url,
                "title": item.get("title", ""),
                "text": text,
                "_provider": "ddgs",
            }
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        for page in ex.map(fetch, results[:3]):
            if page:
                pages.append(page)

    return {
        "results": results,
        "pages": pages,
        "provider": "ddgs",
    }


def _iter_evidence(web_data):
    for item in list((web_data or {}).get("results", []) or []) + list(
        (web_data or {}).get("pages", []) or []
    ):
        if not isinstance(item, dict):
            continue

        title = v3.item_title(item)
        snippet = v3.item_snippet(item)
        body = v3.item_body(item)
        url = v3.item_url(item)
        relevance = float(item.get("_jarvis_relevance_score", 0.0) or 0.0)
        authority = v3.source_authority(url)

        text = "\n".join(x for x in (title, snippet, body) if x)

        yield item, text, url, relevance, authority


def _segments(text):
    chunks = re.split(r"(?:\n+|(?<=[.!?])\s+)", str(text or ""))
    return [re.sub(r"\s+", " ", x).strip() for x in chunks if x.strip()]


def precision_candidates(web_data, query):
    answer_type = expected_answer_type(query)
    entity = v3.extract_primary_entity(query)
    terms = v3.query_terms(entity or query)

    candidates = []

    if answer_type not in {"date", "price", "version"}:
        return candidates

    pattern = {
        "date": DATE_RE,
        "price": PRICE_RE,
        "version": VERSION_RE,
    }[answer_type]

    for _, text, url, relevance, authority in _iter_evidence(web_data):
        for segment in _segments(text):
            matches = list(pattern.finditer(segment))

            if not matches:
                continue

            low = segment.lower()
            score = relevance * 0.6 + authority * 1.25

            if terms:
                score += sum(1.0 for t in terms if t.lower() in low)

            if answer_type == "date":
                if any(word in low for word in RELEASE_WORDS):
                    score += 8.0

                if any(word in low for word in PUBLICATION_WORDS):
                    score -= 2.5

            if answer_type == "price":
                if any(x in low for x in ("price", "cost", "starting at", "available for")):
                    score += 6.0

            if answer_type == "version":
                if any(x in low for x in ("latest", "current", "version", "release")):
                    score += 6.0

            for match in matches:
                candidates.append({
                    "value": match.group(0),
                    "segment": segment[:500],
                    "url": url,
                    "score": round(score, 2),
                    "authority": round(authority, 2),
                })

    candidates.sort(
        key=lambda x: float(x.get("score", 0.0)),
        reverse=True,
    )

    deduped = []
    seen = set()

    for item in candidates:
        key = item["value"].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped[:10]


def precision_satisfied(web_data, query):
    answer_type = expected_answer_type(query)

    if answer_type in {"date", "price", "version"}:
        return bool(precision_candidates(web_data, query))

    return bool(
        (web_data or {}).get("results")
        or (web_data or {}).get("pages")
    )


def _merge(existing, incoming, key_func):
    seen = {key_func(x) for x in existing if key_func(x)}

    for item in incoming:
        if not isinstance(item, dict):
            continue

        key = key_func(item)
        if key and key in seen:
            continue

        existing.append(item)

        if key:
            seen.add(key)


def research_with_precision(
    query,
    research_func,
    max_results=8,
    max_attempts=5,
    use_ddgs_fallback=True,
):
    entity = v3.extract_primary_entity(query)
    answer_type = expected_answer_type(query)
    variants = smart_query_variants(query, max_variants=max_attempts)

    merged_results = []
    merged_pages = []
    attempts = []
    discarded_results = 0
    discarded_pages = 0

    # Exact current-fact queries use relevance but do not enforce strict
    # same-string entity matching. This allows GTA 6 -> Grand Theft Auto VI,
    # product nicknames, acronyms, etc. Primary/authoritative sources still
    # receive authority weighting.
    strict_entity = (
        entity
        if answer_type in {"generic", "latest"}
        else ""
    )

    for variant in variants:
        try:
            raw = research_func(
                variant,
                max_results=max_results,
            )
        except Exception as e:
            attempts.append({
                "query": variant,
                "provider": "primary",
                "error": str(e),
            })
            continue

        filtered, diag = v3.filter_web_data(
            raw,
            query=query,
            entity=strict_entity,
        )

        _merge(
            merged_results,
            filtered.get("results", []) or [],
            v3._result_key,
        )
        _merge(
            merged_pages,
            filtered.get("pages", []) or [],
            v3._page_key,
        )

        discarded_results += int(diag.get("discarded_results", 0))
        discarded_pages += int(diag.get("discarded_pages", 0))

        snapshot = {
            "results": merged_results,
            "pages": merged_pages,
        }

        attempts.append({
            "query": variant,
            "provider": "primary",
            "relevant_results": diag.get("relevant_results", 0),
            "relevant_pages": diag.get("relevant_pages", 0),
            "precision_satisfied": precision_satisfied(snapshot, query),
        })

        if precision_satisfied(snapshot, query):
            break

    current = {
        "results": merged_results,
        "pages": merged_pages,
    }

    # Optional second provider. This is deliberately a fallback rather than a
    # requirement, so Jarvis still works if DDGS is not installed.
    if use_ddgs_fallback and not precision_satisfied(current, query):
        for variant in variants[:3]:
            raw = ddgs_research(
                variant,
                max_results=max_results,
            )

            if not raw.get("results") and not raw.get("pages"):
                continue

            filtered, diag = v3.filter_web_data(
                raw,
                query=query,
                entity=strict_entity,
            )

            _merge(
                merged_results,
                filtered.get("results", []) or [],
                v3._result_key,
            )
            _merge(
                merged_pages,
                filtered.get("pages", []) or [],
                v3._page_key,
            )

            discarded_results += int(diag.get("discarded_results", 0))
            discarded_pages += int(diag.get("discarded_pages", 0))

            current = {
                "results": merged_results,
                "pages": merged_pages,
            }

            attempts.append({
                "query": variant,
                "provider": "ddgs",
                "relevant_results": diag.get("relevant_results", 0),
                "relevant_pages": diag.get("relevant_pages", 0),
                "precision_satisfied": precision_satisfied(current, query),
            })

            if precision_satisfied(current, query):
                break

    merged_results.sort(
        key=lambda x: float(x.get("_jarvis_relevance_score", 0.0)),
        reverse=True,
    )
    merged_pages.sort(
        key=lambda x: float(x.get("_jarvis_relevance_score", 0.0)),
        reverse=True,
    )

    web_data = {
        "results": merged_results,
        "pages": merged_pages,
    }

    candidates = precision_candidates(web_data, query)

    return {
        "query": query,
        "entity": entity,
        "web_data": web_data,
        "diagnostics": {
            "version": VERSION,
            "entity": entity,
            "expected_answer_type": answer_type,
            "query_variants": variants,
            "attempts": attempts,
            "retry_count": max(0, len(attempts) - 1),
            "relevant_results": len(merged_results),
            "relevant_pages": len(merged_pages),
            "discarded_results": discarded_results,
            "discarded_pages": discarded_pages,
            "precision_satisfied": precision_satisfied(web_data, query),
            "precision_candidates": candidates[:5],
            "public_relevance_ok": bool(merged_results or merged_pages),
        },
    }


def direct_precision_plan(query, web_data, spoken_name="Sir"):
    answer_type = expected_answer_type(query)
    candidates = precision_candidates(web_data, query)

    if not candidates:
        return None

    best = candidates[0]

    # Require decent evidence. Authority/relevance/semantic trigger weights
    # make official release statements score comfortably above article dates.
    if float(best.get("score", 0.0)) < 6.0:
        return None

    entity = v3.extract_primary_entity(query)
    value = best["value"]

    if answer_type == "date":
        subject = entity or "It"
        reply = f"{subject} releases on {value}, {spoken_name}."

    elif answer_type == "price":
        subject = entity or "It"
        reply = f"{subject} is listed at {value}, {spoken_name}."

    elif answer_type == "version":
        subject = entity or "The current version"
        reply = f"{subject}: {value}, {spoken_name}."

    else:
        return None

    return {
        "mode": "chat",
        "reply": reply,
        "steps": [],
        "_precision_source": best.get("url", ""),
        "_precision_score": best.get("score", 0.0),
    }


def diagnostics_line(diag):
    return (
        "Search Intelligence V4: "
        f"type={diag.get('expected_answer_type', '-')}; "
        f"relevant={diag.get('relevant_results', 0) + diag.get('relevant_pages', 0)}; "
        f"discarded={diag.get('discarded_results', 0) + diag.get('discarded_pages', 0)}; "
        f"retries={diag.get('retry_count', 0)}; "
        f"precision={'yes' if diag.get('precision_satisfied') else 'no'}"
    )
