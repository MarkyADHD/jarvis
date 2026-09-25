"""World clock: "what time is it in <place>" style questions.

Before this existed, ANY time question got routed to local_date_time_fast
in jarvis_app.py, which matches on the substring "what time is it" --
including inside "what time is it in India" -- and answered with the
machine's own local time, silently ignoring the location. When the
phrasing didn't happen to match that substring at all, the request fell
through everything else and landed on a generic web search, which for a
plain "time in india" query returns scraped junk rather than a real
answer (confirmed live: exactly the failure reported for India).

This is a real timezone lookup (Python's stdlib zoneinfo, backed by the
tzdata package since Windows ships no system timezone database at all --
without it zoneinfo raises ZoneInfoNotFoundError for every key). No
network call, no API key, no dependency on web search returning anything
sane: a fixed country/city -> IANA zone table covers the vast majority of
real "what time is it in X" questions outright.
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Deliberately covers whole countries by their single dominant zone where
# one exists, and named cities where a country spans several (US, Canada,
# Russia, Australia...) or where people are more likely to ask by city.
# Lowercase, spaces only (matches normalize_transcript's output).
PLACE_TIMEZONES = {
    # South Asia
    "india": "Asia/Kolkata", "delhi": "Asia/Kolkata", "new delhi": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata", "bangalore": "Asia/Kolkata", "bengaluru": "Asia/Kolkata",
    "pakistan": "Asia/Karachi", "karachi": "Asia/Karachi", "islamabad": "Asia/Karachi",
    "bangladesh": "Asia/Dhaka", "dhaka": "Asia/Dhaka",
    "sri lanka": "Asia/Colombo", "nepal": "Asia/Kathmandu",
    # East / Southeast Asia
    "china": "Asia/Shanghai", "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong", "taiwan": "Asia/Taipei", "taipei": "Asia/Taipei",
    "japan": "Asia/Tokyo", "tokyo": "Asia/Tokyo",
    "south korea": "Asia/Seoul", "korea": "Asia/Seoul", "seoul": "Asia/Seoul",
    "north korea": "Asia/Pyongyang",
    "singapore": "Asia/Singapore", "malaysia": "Asia/Kuala_Lumpur",
    "kuala lumpur": "Asia/Kuala_Lumpur", "thailand": "Asia/Bangkok",
    "bangkok": "Asia/Bangkok", "vietnam": "Asia/Ho_Chi_Minh",
    "philippines": "Asia/Manila", "manila": "Asia/Manila",
    "indonesia": "Asia/Jakarta", "jakarta": "Asia/Jakarta",
    # Middle East
    "uae": "Asia/Dubai", "dubai": "Asia/Dubai", "abu dhabi": "Asia/Dubai",
    "saudi arabia": "Asia/Riyadh", "riyadh": "Asia/Riyadh",
    "qatar": "Asia/Qatar", "doha": "Asia/Qatar",
    "israel": "Asia/Jerusalem", "jerusalem": "Asia/Jerusalem", "tel aviv": "Asia/Jerusalem",
    "turkey": "Europe/Istanbul", "istanbul": "Europe/Istanbul",
    "iran": "Asia/Tehran", "iraq": "Asia/Baghdad", "jordan": "Asia/Amman",
    # Europe
    "uk": "Europe/London", "united kingdom": "Europe/London",
    "england": "Europe/London", "london": "Europe/London",
    "scotland": "Europe/London", "wales": "Europe/London",
    "ireland": "Europe/Dublin", "dublin": "Europe/Dublin",
    "france": "Europe/Paris", "paris": "Europe/Paris",
    "germany": "Europe/Berlin", "berlin": "Europe/Berlin",
    "spain": "Europe/Madrid", "madrid": "Europe/Madrid",
    "italy": "Europe/Rome", "rome": "Europe/Rome",
    "portugal": "Europe/Lisbon", "lisbon": "Europe/Lisbon",
    "netherlands": "Europe/Amsterdam", "amsterdam": "Europe/Amsterdam",
    "belgium": "Europe/Brussels", "brussels": "Europe/Brussels",
    "switzerland": "Europe/Zurich", "zurich": "Europe/Zurich",
    "austria": "Europe/Vienna", "vienna": "Europe/Vienna",
    "sweden": "Europe/Stockholm", "stockholm": "Europe/Stockholm",
    "norway": "Europe/Oslo", "oslo": "Europe/Oslo",
    "denmark": "Europe/Copenhagen", "copenhagen": "Europe/Copenhagen",
    "finland": "Europe/Helsinki", "helsinki": "Europe/Helsinki",
    "poland": "Europe/Warsaw", "warsaw": "Europe/Warsaw",
    "greece": "Europe/Athens", "athens": "Europe/Athens",
    "russia": "Europe/Moscow", "moscow": "Europe/Moscow",
    "ukraine": "Europe/Kyiv", "kyiv": "Europe/Kyiv", "kiev": "Europe/Kyiv",
    "czech republic": "Europe/Prague", "prague": "Europe/Prague",
    "romania": "Europe/Bucharest", "hungary": "Europe/Budapest",
    "iceland": "Atlantic/Reykjavik",
    # Africa
    "egypt": "Africa/Cairo", "cairo": "Africa/Cairo",
    "south africa": "Africa/Johannesburg", "johannesburg": "Africa/Johannesburg",
    "cape town": "Africa/Johannesburg",
    "nigeria": "Africa/Lagos", "lagos": "Africa/Lagos",
    "kenya": "Africa/Nairobi", "nairobi": "Africa/Nairobi",
    "morocco": "Africa/Casablanca", "ethiopia": "Africa/Addis_Ababa",
    "ghana": "Africa/Accra",
    # Oceania
    "australia": "Australia/Sydney", "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne", "brisbane": "Australia/Brisbane",
    "perth": "Australia/Perth", "adelaide": "Australia/Adelaide",
    "new zealand": "Pacific/Auckland", "auckland": "Pacific/Auckland",
    "fiji": "Pacific/Fiji",
    # North America
    "new york": "America/New_York", "new york city": "America/New_York",
    "washington": "America/New_York", "washington dc": "America/New_York",
    "boston": "America/New_York", "miami": "America/New_York",
    "atlanta": "America/New_York", "toronto": "America/Toronto",
    "chicago": "America/Chicago", "dallas": "America/Chicago",
    "houston": "America/Chicago", "mexico city": "America/Mexico_City",
    "mexico": "America/Mexico_City",
    "denver": "America/Denver", "phoenix": "America/Phoenix",
    "los angeles": "America/Los_Angeles", "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles", "vancouver": "America/Vancouver",
    "las vegas": "America/Los_Angeles",
    "canada": "America/Toronto",
    "usa": "America/New_York", "united states": "America/New_York",
    "america": "America/New_York", "us": "America/New_York",
    # South America
    "brazil": "America/Sao_Paulo", "sao paulo": "America/Sao_Paulo",
    "rio de janeiro": "America/Sao_Paulo",
    "argentina": "America/Argentina/Buenos_Aires", "buenos aires": "America/Argentina/Buenos_Aires",
    "chile": "America/Santiago", "colombia": "America/Bogota",
    "peru": "America/Lima",
}

# normalize_transcript() (jarvis_app.py) lowercases, strips punctuation
# (so "what's" -> "what s") and collapses whitespace before anything here
# ever sees the text -- so this deliberately does NOT try to match a
# specific leading phrase like "what is the time", since the apostrophe
# stripping makes those unpredictable ("what s the time", "whats the
# time", ...). It only needs two things to both be true: a time/date/day
# trigger word anywhere, and a trailing "in <place>". Anything that
# doesn't ALSO resolve to a known place in PLACE_TIMEZONES falls straight
# through to None below, so a false trigger (e.g. "remind me in the
# morning" contains no whole-word "time/date/day" anyway) never risks
# fabricating a wrong answer -- it just defers to whatever handles it today.
_TIME_TRIGGER = re.compile(r"\b(?:time|date|day)\b")
_TRAILING_IN_PLACE = re.compile(r"\bin\s+(?P<place>[a-z][a-z\s]*)$")


def _extract_place(command: str):
    command = str(command or "")
    if not _TIME_TRIGGER.search(command):
        return None
    match = _TRAILING_IN_PLACE.search(command)
    if not match:
        return None
    place = match.group("place").strip()
    return place or None


def resolve_timezone(place: str):
    """Place name (any case/spacing) -> IANA zone name, or None if this
    curated table doesn't know it. Never raises."""
    key = " ".join(str(place or "").lower().split())
    return PLACE_TIMEZONES.get(key)


def is_world_time_question(command: str) -> bool:
    return _extract_place(command) is not None


def world_time_fast(command, spoken_name="Sir"):
    """Returns a chat plan for "what time/day is it in <place>" when the
    place is one this table knows, else None so the caller can try
    something else (rather than silently answering with local time, or
    silently answering nothing)."""
    place = _extract_place(command)
    if not place:
        return None

    zone_name = resolve_timezone(place)
    if not zone_name:
        return None

    wants_day = "day" in command and "time" not in command and "date" not in command
    wants_date = "date" in command

    try:
        now = datetime.now(ZoneInfo(zone_name))
    except ZoneInfoNotFoundError:
        return None

    place_title = place.title()
    if wants_day:
        reply = now.strftime(f"It's %A in {place_title}, {spoken_name}.")
    elif wants_date:
        reply = now.strftime(f"It's %A %d %B %Y in {place_title}, {spoken_name}.")
    else:
        reply = now.strftime(f"It's %H:%M in {place_title}, {spoken_name}.")

    return {"mode": "chat", "reply": reply, "steps": []}
