"""
Jarvis Maps V1 -- "directions to X" / "show me X on the map".

Opens Google Maps in the browser. Directions leave the origin blank so
Maps fills in the device's own location, the same no-precise-GPS choice
jarvis_uber_v1 makes.
"""
import re
import urllib.parse
import webbrowser

_DIRECTIONS = re.compile(
    r"^(?:get me |give me |show me |find )?(?:directions|a route|the route|the way) to (.+)$"
    r"|^how do i get to (.+)$"
    r"|^navigate to (.+)$",
    re.IGNORECASE,
)
_SHOW = re.compile(
    r"^(?:show me|find|where is|where's) (.+?) on (?:the )?(?:map|maps|google maps)$"
    r"|^(?:open )?(?:google )?maps? (?:for|of) (.+)$",
    re.IGNORECASE,
)


def _first_group(m):
    return next((g for g in m.groups() if g), "").strip(" .?!")


def maps_command_fast(command, spoken_name="Sir", app_module=None):
    c = str(command or "").strip()

    m = _DIRECTIONS.search(c)
    if m:
        place = _first_group(m)
        if not place:
            return None
        url = "https://www.google.com/maps/dir/?api=1&destination=" + urllib.parse.quote(place)
        webbrowser.open(url)
        return {"mode": "chat", "reply": f"Directions to {place} are up on Google Maps, {spoken_name}.", "steps": []}

    m = _SHOW.search(c)
    if m:
        place = _first_group(m)
        if not place:
            return None
        url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(place)
        webbrowser.open(url)
        return {"mode": "chat", "reply": f"Pulled {place} up on the map, {spoken_name}.", "steps": []}

    return None
