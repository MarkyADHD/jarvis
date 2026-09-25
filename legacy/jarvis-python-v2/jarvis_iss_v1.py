"""
Jarvis Space V1 -- "where is the ISS" / "how many people are in space".

Free, keyless APIs: wheretheiss.at for position, open-notify for crew,
Nominatim (same polite User-Agent as jarvis_uber_v1) to name the spot
underneath. Over open ocean Nominatim finds nothing, which we say plainly.
"""
import re

import requests

ISS_URL = "https://api.wheretheiss.at/v1/satellites/25544"
# open-notify's astros feed is stale (still lists 2024 crews); this one is maintained.
ASTROS_URL = "https://corquaid.github.io/international-space-station-APIs/JSON/people-in-space.json"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
HEADERS = {"User-Agent": "Jarvis-Personal-Assistant/1.0 (personal use)"}

_WHERE = re.compile(r"\b(?:where(?:'s| is)|track|locate)\b.*\b(?:iss|space station|international space station)\b", re.IGNORECASE)
_CREW = re.compile(r"\bhow many (?:people|astronauts|humans) (?:are )?(?:in|on) (?:space|the iss|the space station)\b|\bwho(?:'s| is) in space\b", re.IGNORECASE)


def _place_below(lat, lon):
    try:
        r = requests.get(NOMINATIM_REVERSE, params={"lat": lat, "lon": lon, "format": "json", "zoom": 3}, headers=HEADERS, timeout=6)
        data = r.json()
        addr = data.get("address") or {}
        return addr.get("country") or addr.get("state") or data.get("display_name")
    except Exception:
        return None


def iss_command_fast(command, spoken_name="Sir", app_module=None):
    c = str(command or "").strip()

    if _CREW.search(c):
        try:
            data = requests.get(ASTROS_URL, timeout=8).json()
        except Exception:
            return None
        people = data.get("people") or []
        count = data.get("number") or len(people)
        if not count:
            return None
        names = ", ".join(p.get("name", "") for p in people[:10] if p.get("name"))
        tail = f": {names}" if names else ""
        return {"mode": "chat", "reply": f"There are {count} people in space right now, {spoken_name}{tail}.", "steps": []}

    if _WHERE.search(c):
        try:
            d = requests.get(ISS_URL, timeout=6).json()
            lat, lon = float(d["latitude"]), float(d["longitude"])
            alt, vel = round(float(d["altitude"])), round(float(d["velocity"]))
        except Exception:
            return None
        below = _place_below(lat, lon)
        where = f"over {below}" if below else "over open ocean"
        return {
            "mode": "chat",
            "reply": f"The ISS is {where} right now, {spoken_name} -- about {alt} km up, doing roughly {vel:,} km/h.",
            "steps": [],
        }

    return None
