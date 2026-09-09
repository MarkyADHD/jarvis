import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


GOOGLE_API_KEY_ENV = "JARVIS_GOOGLE_API_KEY"
GOOGLE_CX_ENV = "JARVIS_GOOGLE_CX"

SEARCH_TIMEOUT_SECONDS = 15
# Was 12 -- confirmed live as a real contributor to "sometimes 40 second"
# replies: a single slow/unresponsive page ate a full 12s before giving
# up, sequentially, once per page. A legitimate page responds in well
# under this; anything actually taking 12s is far more likely dead or
# blocking outright than "about to respond a moment later", so failing
# faster costs almost nothing in practice.
PAGE_TIMEOUT_SECONDS = 6
MAX_PAGE_CHARS = 7000


def clean_text(text):
    text = re.sub(r"\s+", " ", str(text or ""))
    return text.strip()


def strip_html(html):
    text = re.sub(r"<script.*?</script>", " ", str(html or ""), flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    return clean_text(text)


def google_credentials_available():
    api_key = os.getenv(GOOGLE_API_KEY_ENV, "").strip()
    cx = os.getenv(GOOGLE_CX_ENV, "").strip()
    return bool(api_key and cx)


def search_google_custom(query, max_results=5):
    query = str(query).strip()

    if not query:
        return []

    api_key = os.getenv(GOOGLE_API_KEY_ENV, "").strip()
    cx = os.getenv(GOOGLE_CX_ENV, "").strip()

    if not api_key or not cx:
        raise RuntimeError("Google Custom Search missing JARVIS_GOOGLE_API_KEY or JARVIS_GOOGLE_CX.")

    response = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": max(1, min(int(max_results), 10)),
            "safe": "active",
        },
        headers={"User-Agent": "JarvisLocalAssistant/1.0"},
        timeout=SEARCH_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    data = response.json()

    results = []

    for item in data.get("items", []):
        title = clean_text(item.get("title"))
        url = clean_text(item.get("link"))
        snippet = clean_text(item.get("snippet"))

        if title and url:
            results.append({
                "source": "google_custom_search",
                "title": title,
                "url": url,
                "snippet": snippet,
            })

    return results


def search_google_news_rss(query, max_results=5):
    query = str(query).strip()

    if not query:
        return []

    encoded = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-GB&gl=GB&ceid=GB:en"

    response = requests.get(
        url,
        headers={"User-Agent": "JarvisLocalAssistant/1.0"},
        timeout=SEARCH_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    root = ET.fromstring(response.content)

    results = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        link = clean_text(item.findtext("link"))
        snippet = strip_html(item.findtext("description"))
        published = clean_text(item.findtext("pubDate"))

        if title and link:
            results.append({
                "source": "google_news_rss",
                "title": title,
                "url": link,
                "snippet": snippet,
                "published": published,
            })

        if len(results) >= max_results:
            break

    return results


def search_google_web_light(query, max_results=5):
    query = str(query).strip()

    if not query:
        return []

    response = requests.get(
        "https://www.google.com/search",
        params={"q": query, "hl": "en-GB", "gl": "GB"},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept-Language": "en-GB,en;q=0.9",
        },
        timeout=SEARCH_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    html = response.text

    if "Our systems have detected unusual traffic" in html:
        raise RuntimeError("Google web fallback was blocked.")

    raw_links = re.findall(r"/url\?q=(https?://[^&]+)&", html)
    results = []
    seen = set()

    for raw_link in raw_links:
        link = urllib.parse.unquote(raw_link)

        if not link.startswith("http"):
            continue

        if "google." in link or "webcache" in link:
            continue

        if link in seen:
            continue

        seen.add(link)

        domain = re.sub(r"^https?://", "", link).split("/")[0]

        results.append({
            "source": "google_web_light",
            "title": domain,
            "url": link,
            "snippet": "Google result found. Snippet unavailable from fallback parser.",
        })

        if len(results) >= max_results:
            break

    return results


def search_bing_rss(query, max_results=5):
    query = str(query).strip()

    if not query:
        return []

    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?format=rss&q={encoded}"

    response = requests.get(
        url,
        headers={"User-Agent": "JarvisLocalAssistant/1.0"},
        timeout=SEARCH_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    root = ET.fromstring(response.content)

    results = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        link = clean_text(item.findtext("link"))
        snippet = strip_html(item.findtext("description"))
        published = clean_text(item.findtext("pubDate"))

        if title and link:
            results.append({
                "source": "bing_rss_fallback",
                "title": title,
                "url": link,
                "snippet": snippet,
                "published": published,
            })

        if len(results) >= max_results:
            break

    return results


def looks_like_handle(query):
    q = str(query).strip()
    cleaned = q.lower().replace("@", "")
    return bool(re.fullmatch(r"[a-z0-9_.-]{3,32}", cleaned))


def handle_profile_candidates(query):
    handle = str(query).strip().replace("@", "")
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "", handle)

    if not cleaned:
        return []

    return [
        {
            "source": "direct_profile_candidate",
            "title": f"Possible Twitch profile for {cleaned}",
            "url": f"https://www.twitch.tv/{cleaned}",
            "snippet": "Direct profile candidate based on the handle. Verify on the page before treating as confirmed.",
        },
        {
            "source": "direct_profile_candidate",
            "title": f"Possible YouTube handle for {cleaned}",
            "url": f"https://www.youtube.com/@{cleaned}",
            "snippet": "Direct profile candidate based on the handle. Verify on the page before treating as confirmed.",
        },
        {
            "source": "direct_profile_candidate",
            "title": f"Possible TikTok profile for {cleaned}",
            "url": f"https://www.tiktok.com/@{cleaned}",
            "snippet": "Direct profile candidate based on the handle. Verify on the page before treating as confirmed.",
        },
        {
            "source": "direct_profile_candidate",
            "title": f"Possible Instagram profile for {cleaned}",
            "url": f"https://www.instagram.com/{cleaned}/",
            "snippet": "Direct profile candidate based on the handle. Verify on the page before treating as confirmed.",
        },
        {
            "source": "direct_profile_candidate",
            "title": f"Possible Kick profile for {cleaned}",
            "url": f"https://kick.com/{cleaned}",
            "snippet": "Direct profile candidate based on the handle. Verify on the page before treating as confirmed.",
        },
    ]


def dedupe_results(results):
    clean = []
    seen_urls = set()
    seen_titles = set()

    for result in results:
        url = clean_text(result.get("url"))
        title = clean_text(result.get("title"))

        if not url or not title:
            continue

        key_url = url.rstrip("/").lower()
        key_title = title.lower()

        if key_url in seen_urls or key_title in seen_titles:
            continue

        seen_urls.add(key_url)
        seen_titles.add(key_title)

        clean.append(result)

    return clean


def search_google(query, max_results=5):
    query = str(query).strip()
    lowered = query.lower()
    errors = []
    results = []

    if google_credentials_available():
        try:
            results.extend(search_google_custom(query, max_results=max_results))
        except Exception as e:
            errors.append(f"Google Custom Search failed: {e}")
    else:
        errors.append("Google Custom Search credentials not found. Using fallback search.")

    news_words = [
        "latest",
        "current",
        "today",
        "news",
        "released",
        "release",
        "update",
        "announced",
        "rumour",
        "rumor",
    ]

    if any(word in lowered for word in news_words):
        try:
            results.extend(search_google_news_rss(query, max_results=max_results))
        except Exception as e:
            errors.append(f"Google News RSS failed: {e}")

    if len(results) < max_results:
        try:
            results.extend(search_google_web_light(query, max_results=max_results))
        except Exception as e:
            errors.append(f"Google web fallback failed: {e}")

    if len(results) < max_results:
        try:
            results.extend(search_bing_rss(query, max_results=max_results))
        except Exception as e:
            errors.append(f"Bing RSS emergency fallback failed: {e}")

    if looks_like_handle(query):
        results.extend(handle_profile_candidates(query))

    results = dedupe_results(results)

    if not results and errors:
        raise RuntimeError(" | ".join(errors))

    return results[:max_results]


def read_webpage(url):
    url = str(url).strip()

    response = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept-Language": "en-GB,en;q=0.9",
        },
        timeout=PAGE_TIMEOUT_SECONDS,
    )

    response.raise_for_status()

    html = response.text

    title = ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)

    if title_match:
        title = strip_html(title_match.group(1))

    html = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<nav.*?</nav>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<footer.*?</footer>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<header.*?</header>", " ", html, flags=re.I | re.S)

    text = strip_html(html)

    return {
        "title": title,
        "url": url,
        "text": text[:MAX_PAGE_CHARS],
    }


def web_research(query, max_results=5):
    query = str(query).strip()

    output = {
        "engine": "google_first_plus_fallbacks",
        "query": query,
        "results": [],
        "pages": [],
        "setup_needed": False,
        "notes": [],
    }

    try:
        output["results"] = search_google(query, max_results=max_results)
    except Exception as e:
        output["notes"].append(str(e))

        if "credentials" in str(e).lower() or "api" in str(e).lower() or "cx" in str(e).lower():
            output["setup_needed"] = True

    # Fetched concurrently, not one at a time -- these are independent
    # HTTP requests to different sites, so the old sequential loop made
    # total latency the SUM of every page's fetch time (worst case,
    # 3 x PAGE_TIMEOUT_SECONDS if all three happened to be slow) instead
    # of just the slowest one. Confirmed live as a real contributor to
    # "sometimes 40 second" replies. Order preserved in the output
    # (submitted and collected by original result order) even though
    # they don't necessarily finish in that order, so this doesn't
    # quietly change downstream ranking/precision behaviour.
    to_fetch = [
        r for r in output["results"][:3]
        if str(r.get("source", "")) != "direct_profile_candidate"
    ]

    if to_fetch:
        with ThreadPoolExecutor(max_workers=len(to_fetch)) as pool:
            futures = {pool.submit(read_webpage, r["url"]): r for r in to_fetch}
            pages_by_result = {}
            for future in as_completed(futures):
                result = futures[future]
                try:
                    pages_by_result[id(result)] = future.result()
                except Exception as e:
                    output["notes"].append(f"Could not read page: {result.get('url')} | {e}")
            for result in to_fetch:
                page = pages_by_result.get(id(result))
                if page is not None:
                    output["pages"].append(page)

    return output


def format_web_context(web_data):
    if not web_data:
        return ""

    lines = []

    lines.append(f"Search engine: {web_data.get('engine', 'google_first_plus_fallbacks')}")
    lines.append(f"Live web research for: {web_data.get('query', '')}")

    if web_data.get("setup_needed"):
        lines.append("Google Custom Search API may not be configured. Fallback results may be limited.")

    notes = web_data.get("notes", [])
    if notes:
        lines.append("\nSearch notes:")
        for note in notes[:5]:
            lines.append(f"- {note}")

    results = web_data.get("results", [])
    pages = web_data.get("pages", [])

    if results:
        lines.append("\nSearch results:")
        for i, result in enumerate(results, start=1):
            lines.append(f"{i}. {result.get('title', '')}")
            lines.append(f"   Source: {result.get('source', '')}")
            lines.append(f"   URL: {result.get('url', '')}")

            if result.get("published"):
                lines.append(f"   Published: {result.get('published', '')}")

            if result.get("snippet"):
                lines.append(f"   Snippet: {result.get('snippet', '')}")

    if pages:
        lines.append("\nReadable page extracts:")
        for i, page in enumerate(pages, start=1):
            lines.append(f"{i}. {page.get('title', '')}")
            lines.append(f"   URL: {page.get('url', '')}")
            lines.append(f"   Text: {page.get('text', '')[:2500]}")

    if not results and not pages:
        lines.append("\nNo useful web results were found.")

    return "\n".join(lines)
