
"""
Jarvis Operator V2.1 Hybrid Direct Control

Fixes:
- Natural Twitch/search-bar wording now bypasses vision.
- "enter into the search bar markyadhd and press enter" is converted into a direct Twitch search URL.
- Adds a side-effect-free should_handle() so web routing does not accidentally perform actions.
- Falls back to Operator V1 vision only for vague non-browser clicking tasks.
"""

import re
import subprocess
import time
import urllib.parse
import webbrowser

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import pyperclip
except Exception:
    pyperclip = None

try:
    import jarvis_desktop_v2 as desktop
except Exception:
    desktop = None

try:
    import jarvis_operator_v1 as operator_v1
except Exception:
    operator_v1 = None

try:
    import jarvis_link_intelligence_v1 as link_v1
except Exception:
    link_v1 = None


WAKE_WORDS = {
    "jarvis", "jervis", "javis", "javas", "jarvus", "travis", "charvis", "service"
}

SITE_URLS = {
    "twitch dashboard": "https://dashboard.twitch.tv",
    "youtube studio": "https://studio.youtube.com",
    "twitch": "https://www.twitch.tv",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chatgpt.com",
    "instagram": "https://www.instagram.com",
    "tiktok": "https://www.tiktok.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "amazon": "https://www.amazon.co.uk",
    "etsy": "https://www.etsy.com/uk",
    "ebay": "https://www.ebay.co.uk",
    "netflix": "https://www.netflix.com",
    "disney": "https://www.disneyplus.com",
    "prime": "https://www.primevideo.com",
    "kick": "https://kick.com",
    "streamelements": "https://streamelements.com",
}

SEARCH_URLS = {
    "twitch": "https://www.twitch.tv/search?term={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "google": "https://www.google.com/search?q={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",
    "amazon": "https://www.amazon.co.uk/s?k={query}",
    "etsy": "https://www.etsy.com/uk/search?q={query}",
    "ebay": "https://www.ebay.co.uk/sch/i.html?_nkw={query}",
    "x": "https://x.com/search?q={query}&src=typed_query",
    "twitter": "https://x.com/search?q={query}&src=typed_query",
}

SITE_WORDS = set(SEARCH_URLS.keys()).union(SITE_URLS.keys())

# Sites where "open X on <site>" means a specific channel/profile, not the
# bare homepage -- mapped to jarvis_link_intelligence_v1's platform keys so
# a named channel gets properly resolved instead of silently discarded.
PROFILE_PLATFORMS = {
    "twitch": "twitch",
    "kick": "kick",
    "instagram": "instagram",
    "tiktok": "tiktok",
    "x": "x",
    "twitter": "x",
    "youtube": "youtube",
}

# The user's own handle, used when they say "my channel"/"my page" etc.
# with nothing else to resolve.
OWN_HANDLE = "MarkyADHD"

_FILLER_WORDS = {
    "my", "me", "mine", "myself", "own", "channel", "page", "profile",
    "account", "handle", "on", "in", "to", "at", "the", "a", "for",
}

RISKY_FINAL_WORDS = [
    "buy",
    "purchase",
    "checkout",
    "pay",
    "payment",
    "send",
    "post",
    "tweet",
    "message",
    "email",
    "delete",
    "remove",
    "uninstall",
    "format",
    "bank",
    "password",
    "2fa",
    "verification code",
    "private key",
    "token",
]


def normalise(text):
    text = str(text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s.,!?@:/\\+\-.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_wake(text):
    c = normalise(text)
    parts = c.split()

    if parts and parts[0] in WAKE_WORDS:
        return " ".join(parts[1:]).strip()

    return c


def clean_take_control(text):
    c = strip_wake(text)

    removals = [
        "could you",
        "please",
        "can you",
        "as you can see",
        "i am on",
        "im on",
        "i m on",
        "take control of my pc and",
        "take control of the pc and",
        "take control and",
        "take control",
        "control my pc and",
        "control the pc and",
        "control my computer and",
        "use my pc and",
        "use the pc and",
        "use my computer and",
        "use the computer and",
        "operate my pc and",
        "operate the pc and",
        "do it on my pc and",
        "do it on the pc and",
        "control my pc",
        "control the pc",
        "control my computer",
        "use my pc",
        "use the pc",
        "use my computer",
        "use the computer",
        "operate my pc",
        "operate the pc",
        "do it on my pc",
        "do it on the pc",
    ]

    for item in removals:
        c = c.replace(item, " ")

    return re.sub(r"\s+", " ", c).strip()


def risky_goal(text):
    c = normalise(text)
    return any(word in c for word in RISKY_FINAL_WORDS)


def browser_related(text):
    c = normalise(text)
    return any(site in c for site in SITE_WORDS) or "search bar" in c or "search box" in c


def encode_query(query):
    return urllib.parse.quote_plus(str(query or "").strip())


def open_url_reliable(url):
    try:
        webbrowser.open(url, new=2, autoraise=True)
        return True
    except Exception:
        pass

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        return True
    except Exception:
        return False


def clipboard_set(text):
    text = str(text)

    if pyperclip is not None:
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            pass

    try:
        safe = text.replace("'", "''")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{safe}'"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return True
    except Exception:
        return False


def paste_text(text):
    if pyautogui is None:
        return False

    if not clipboard_set(text):
        return False

    try:
        pyautogui.hotkey("ctrl", "v")
        return True
    except Exception:
        return False


def focus_browser():
    if desktop is not None:
        for name in ["chrome", "edge", "firefox"]:
            try:
                if desktop.focus_existing_app(name):
                    return True
            except Exception:
                pass

    return False


def navigate_active_browser(url):
    if pyautogui is None:
        return False

    if not focus_browser():
        return False

    if not clipboard_set(url):
        return False

    try:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.05)
        pyautogui.press("enter")
        return True
    except Exception:
        return False


def open_url(url):
    if navigate_active_browser(url):
        return True

    return open_url_reliable(url)


def clean_query_text(query):
    query = str(query or "").strip()
    query = normalise(query)

    query = re.sub(r"\b(and then|then)?\s*press\s+enter\b.*$", "", query).strip()
    query = re.sub(r"\b(and then|then)?\s*hit\s+enter\b.*$", "", query).strip()
    query = re.sub(r"\b(and then|then)?\s*click\s+enter\b.*$", "", query).strip()
    query = re.sub(r"\binto\s+the\s+search\s+(bar|box)\b", "", query).strip()
    query = re.sub(r"\bin\s+the\s+search\s+(bar|box)\b", "", query).strip()
    query = re.sub(r"\s+", " ", query).strip(" .,!?:;-")

    return query


def parse_search_bar_command(command):
    c = clean_take_control(command)

    if "search bar" not in c and "search box" not in c:
        return None, None

    site = "google"
    for candidate in ["twitch", "youtube", "google", "reddit", "amazon", "etsy", "ebay", "twitter", "x"]:
        if candidate in c:
            site = candidate
            break

    patterns = [
        r"(?:enter|type|put|write|paste)\s+(?:into\s+)?(?:the\s+)?(?:\w+\s+)?search\s+(?:bar|box)\s+(.+)$",
        r"(?:search\s+(?:bar|box))\s+(?:for\s+)?(.+)$",
        r"(?:in\s+the\s+search\s+(?:bar|box))\s+(?:type\s+|enter\s+|put\s+)?(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, c)
        if not match:
            continue

        query = clean_query_text(match.group(1))
        if query:
            return site, query

    match = re.search(r"search\s+(?:bar|box)\s+(.+)$", c)
    if match:
        query = clean_query_text(match.group(1))
        if query:
            return site, query

    return site, None


def parse_search_command(command):
    c = clean_take_control(command)

    site, query = parse_search_bar_command(c)
    if site and query:
        return site, query

    patterns = [
        r"^(?:search|look up|find)\s+(?:on\s+)?(twitch|youtube|google|reddit|amazon|etsy|ebay|twitter|x)\s+(?:for\s+)?(.+)$",
        r"^(?:search|look up|find)\s+(.+?)\s+(?:on|in)\s+(twitch|youtube|google|reddit|amazon|etsy|ebay|twitter|x)$",
        r"^(twitch|youtube|google|reddit|amazon|etsy|ebay|twitter|x)\s+search\s+(.+)$",
        r"^(?:search|look up|find|google)\s+(.+)$",
    ]

    for idx, pattern in enumerate(patterns):
        match = re.search(pattern, c)
        if not match:
            continue

        if idx == 0:
            return match.group(1).strip(), clean_query_text(match.group(2))

        if idx == 1:
            return match.group(2).strip(), clean_query_text(match.group(1))

        if idx == 2:
            return match.group(1).strip(), clean_query_text(match.group(2))

        if idx == 3:
            return "google", clean_query_text(match.group(1))

    return None, None


def parse_open_site(command, app_module=None):
    c = clean_take_control(command)

    match = re.search(r"^(?:open|go to|load|bring up|show me)\s+(.+)$", c)
    if not match:
        return None, None

    target = match.group(1).strip()
    target = re.sub(r"\b(the|website|site|page|app|application|for me|please)\b", " ", target)
    target = re.sub(r"\s+", " ", target).strip()

    if target.startswith("http://") or target.startswith("https://"):
        return target, target

    if "." in target and " " not in target:
        return "https://" + target.replace(" ", ""), target

    for name, url in sorted(SITE_URLS.items(), key=lambda item: len(item[0]), reverse=True):
        if target == name or name in target:
            # A bare site match ("open twitch") -- nothing more to resolve.
            if target == name:
                return url, name

            # "open <something> twitch" / "open twitch <something>": there's
            # leftover text beyond the site name itself. Used to silently
            # collapse to the bare homepage, discarding whatever channel or
            # username the person actually said. Try to resolve it properly
            # instead, on the sites where "a channel" is even a concept.
            remainder = re.sub(rf"\b{re.escape(name)}\b", " ", target)
            remainder = re.sub(r"\s+", " ", remainder).strip()

            profile_platform = PROFILE_PLATFORMS.get(name)

            if remainder and profile_platform and link_v1 is not None:
                remainder_words = [
                    w for w in remainder.split()
                    if w not in _FILLER_WORDS
                ]

                if not remainder_words:
                    # "open my twitch channel" etc -- nothing left but
                    # self-referring filler, so they mean their own page.
                    direct = link_v1.canonical_direct_url(
                        profile_platform, OWN_HANDLE
                    )
                    if direct:
                        return direct, OWN_HANDLE
                elif app_module is not None:
                    entity = " ".join(remainder_words)
                    resolved_url, _method = link_v1.resolve_profile_url(
                        entity, profile_platform, app_module
                    )
                    if resolved_url:
                        return resolved_url, entity

            return url, name

    return None, None


def parse_type_command(command):
    c = clean_take_control(command)

    patterns = [
        r"^type\s+(.+)$",
        r"^paste\s+(.+)$",
        r"^write\s+(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, c)
        if match:
            return match.group(1).strip()

    return None


def should_handle(command):
    c = clean_take_control(command)

    site, query = parse_search_command(c)
    if query:
        return True

    url, label = parse_open_site(c)
    if url:
        return True

    if parse_type_command(c):
        return True

    if desktop is not None:
        try:
            if desktop.parse_open_app(c):
                return True
        except Exception:
            pass

    if operator_v1 is not None:
        try:
            if operator_v1.is_confirmation(c):
                return True
        except Exception:
            pass

    return False


def direct_search_plan(site, query, spoken_name="Sir"):
    site = normalise(site or "google")
    query = clean_query_text(query)

    if not query:
        return {
            "mode": "chat",
            "reply": f"What should I search for, {spoken_name}?",
            "steps": []
        }

    if site not in SEARCH_URLS:
        site = "google"

    url = SEARCH_URLS[site].format(query=encode_query(query))
    ok = open_url(url)

    label = "X" if site in ["x", "twitter"] else site.title()

    if ok:
        return {
            "mode": "action",
            "reply": f"Searching {label} for {query}, {spoken_name}.",
            "steps": []
        }

    return {
        "mode": "chat",
        "reply": f"I couldn’t open the browser search, {spoken_name}.",
        "steps": []
    }


def direct_open_plan(url, label, spoken_name="Sir"):
    ok = open_url(url)

    if ok:
        return {
            "mode": "action",
            "reply": f"Opening {label}, {spoken_name}.",
            "steps": []
        }

    return {
        "mode": "chat",
        "reply": f"I couldn’t open {label}, {spoken_name}.",
        "steps": []
    }


def direct_type_plan(text, spoken_name="Sir"):
    if risky_goal(text):
        return {
            "mode": "chat",
            "reply": f"That might involve a risky action, {spoken_name}. I won’t type/send/post anything risky without clearer confirmation.",
            "steps": []
        }

    if not text:
        return None

    ok = paste_text(text)

    if ok:
        return {
            "mode": "action",
            "reply": f"Typed it, {spoken_name}.",
            "steps": []
        }

    return {
        "mode": "chat",
        "reply": f"I couldn’t paste/type into the active window, {spoken_name}.",
        "steps": []
    }


def direct_app_plan(command, spoken_name="Sir"):
    if desktop is None:
        return None

    c = clean_take_control(command)

    try:
        return desktop.open_app_plan(c, spoken_name)
    except Exception:
        return None


def operator_v2_command_fast(command, spoken_name="Sir", app_module=None):
    c = clean_take_control(command)

    site, query = parse_search_command(c)
    if query:
        return direct_search_plan(site, query, spoken_name)

    if ("search bar" in c or "search box" in c) and browser_related(c):
        return {
            "mode": "chat",
            "reply": f"I can do that directly, {spoken_name}. Say: Jarvis search Twitch for MarkyADHD.",
            "steps": []
        }

    url, label = parse_open_site(c, app_module=app_module)
    if url:
        return direct_open_plan(url, label, spoken_name)

    typed = parse_type_command(c)
    if typed:
        return direct_type_plan(typed, spoken_name)

    app_plan = direct_app_plan(c, spoken_name)
    if app_plan:
        return app_plan

    if operator_v1 is not None:
        try:
            if operator_v1.is_confirmation(command):
                return operator_v1.operator_command_fast(command, spoken_name, app_module)
        except Exception as e:
            return {
                "mode": "chat",
                "reply": f"Operator fallback failed: {e} {spoken_name}.",
                "steps": []
            }

    if browser_related(c):
        return None

    if operator_v1 is not None:
        try:
            if operator_v1.is_operator_request(command):
                return operator_v1.operator_command_fast(command, spoken_name, app_module)
        except Exception as e:
            return {
                "mode": "chat",
                "reply": f"Operator V1 fallback failed: {e} {spoken_name}.",
                "steps": []
            }

    return None


def operator_command_fast(command, spoken_name="Sir", app_module=None):
    return operator_v2_command_fast(command, spoken_name, app_module)
