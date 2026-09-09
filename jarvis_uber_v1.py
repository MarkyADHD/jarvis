"""
Jarvis Uber V1
================

"Get me an Uber to X" -- pre-fills a real Uber ride request and opens it,
rather than pretending to book one autonomously.

WHY NOT REAL AUTONOMOUS BOOKING: investigated Uber's actual API access
for real before building anything. Uber's Riders API (the one that can
actually place and pay for a ride programmatically) has been locked
behind a business-development approval process for years now -- not
self-serve for an individual project, confirmed via Uber's own current
developer docs, not assumed from memory. There is no legitimate path to
"Jarvis silently books you a ride."

What IS genuinely open, no registration/approval/API key needed at all:
Uber's Universal Link deep-link format
(https://m.uber.com/ul/?action=setPickup&...). It opens the real Uber
app or uber.com with pickup and dropoff already filled in -- the user
still taps the final "Request" button themselves in Uber's own app,
where the real price, real payment method, and real confirmation live.
This isn't a workaround forced by the API limitation -- it's actually
the RIGHT design regardless: CLAUDE.md's own safety rules already say
never make purchases autonomously without permission, and a real ride
charges real money. This mechanism makes that final human confirmation
structurally unavoidable rather than something Jarvis has to remember
not to skip.

Pickup uses Uber's own special "my_location" value (the app/device that
opens the link supplies it), never a geocoded address Jarvis has to
determine -- consistent with jarvis_settings_v1.detect_location()'s own
existing choice to never request precise GPS. Only the destination gets
geocoded, via Nominatim (OpenStreetMap, genuinely free, no API key) --
one more service the project doesn't need to add a dependency or a paid
key for.
"""
import re
import time
import urllib.parse

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires a real identifying User-Agent and a
# max of ~1 request/second -- both easily satisfied by an occasional
# voice command, never a bulk/background job.
NOMINATIM_HEADERS = {"User-Agent": "Jarvis-Personal-Assistant/1.0 (personal use)"}

_last_geocode_at = 0.0


def geocode_address(address):
    """Returns (lat, lon, display_name) or None. Best-effort, never
    raises -- a failed geocode should read as "I couldn't find that
    address", not crash the whole request."""
    global _last_geocode_at

    address = str(address or "").strip()
    if not address:
        return None

    # Respect Nominatim's rate policy even under a rapid double-request
    # from the user.
    elapsed = time.time() - _last_geocode_at
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)

    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": address, "format": "json", "limit": 1},
            headers=NOMINATIM_HEADERS,
            timeout=6,
        )
        _last_geocode_at = time.time()
        r.raise_for_status()
        results = r.json()
    except Exception:
        return None

    if not results:
        return None

    top = results[0]
    try:
        return float(top["lat"]), float(top["lon"]), str(top.get("display_name", address))
    except Exception:
        return None


def build_uber_deeplink(dropoff_address):
    """Returns (url, display_name) on success, or (None, error_message)
    on failure (geocoding failed)."""
    geocoded = geocode_address(dropoff_address)
    if not geocoded:
        return None, f"I couldn't find that address: {dropoff_address}"

    lat, lon, display_name = geocoded

    params = [
        ("action", "setPickup"),
        ("pickup[latitude]", "my_location"),
        ("pickup[longitude]", "my_location"),
        ("pickup[nickname]", "my_location"),
        ("dropoff[latitude]", f"{lat}"),
        ("dropoff[longitude]", f"{lon}"),
        ("dropoff[nickname]", dropoff_address.strip()),
        ("dropoff[formatted_address]", display_name),
    ]
    url = "https://m.uber.com/ul/?" + urllib.parse.urlencode(params)
    return url, display_name


TRIGGER_PATTERNS = [
    re.compile(r"^(?:get me|order|call|book|request)\s+(?:an?\s+)?uber\s+to\s+(.+)$", re.IGNORECASE),
    re.compile(r"^uber\s+to\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(?:get me|order|call|book|request)\s+(?:an?\s+)?uber\s+(.+)$", re.IGNORECASE),
]


def _strip_wake(text):
    c = str(text or "").strip()
    low = c.lower()
    for wake in ("jarvis ", "jervis ", "jarviss "):
        if low.startswith(wake):
            return c[len(wake):].strip()
    return c


def is_uber_request(command):
    c = _strip_wake(command)
    return any(p.match(c) for p in TRIGGER_PATTERNS)


def _extract_destination(command):
    c = _strip_wake(command)
    for p in TRIGGER_PATTERNS:
        m = p.match(c)
        if m:
            return m.group(1).strip(" .,!?")
    return ""


def uber_command_fast(command, spoken_name="Sir", app_module=None):
    if not is_uber_request(command):
        return None

    destination = _extract_destination(command)
    if not destination:
        return {
            "mode": "chat",
            "reply": f"Where do you want the Uber to go, {spoken_name}?",
            "steps": [],
        }

    url, result = build_uber_deeplink(destination)
    if not url:
        return {"mode": "chat", "reply": f"{result}, {spoken_name}.", "steps": []}

    try:
        import os
        os.startfile(url)
    except Exception as e:
        return {
            "mode": "chat",
            "reply": f"I built the ride link but couldn't open it, {spoken_name}: {e}",
            "steps": [],
        }

    return {
        "mode": "chat",
        "reply": (
            f"I've opened Uber with a ride to {result}, {spoken_name} -- "
            f"pickup set to your current location. You'll still need to "
            f"confirm and pay in the Uber app yourself, I'm not authorized "
            f"to do that part for you."
        ),
        "steps": [],
    }
