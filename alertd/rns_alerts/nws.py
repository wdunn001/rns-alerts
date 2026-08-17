"""NWS active-alerts client + geocoder for rns-alerts.

Reuses the exact pattern rns-weather already uses: forward-geocode a place via
the local Nominatim (.88), and hit api.weather.gov (US only, no key, but REQUIRES
a descriptive User-Agent or it 403s). The active-alerts endpoint also relays
Non-Weather Emergency Messages (AMBER / Civil Emergency / Evacuation / Shelter-in-
Place / HazMat / Fire), so amber + civil alerts come through the same call.
Everything is stdlib urllib -- no third-party HTTP dep.
"""
import json
import os
import urllib.parse
import urllib.request

NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "http://192.168.1.88:8092").rstrip("/")
NWS_URL = os.environ.get("NWS_URL", "https://api.weather.gov").rstrip("/")
NWS_UA = os.environ.get("NWS_UA", "rns-alerts/0.1 (reticulum quasarke; +https://github.com/wdunn001/rns-alerts)")
HTTP_TIMEOUT = float(os.environ.get("ALERTS_TIMEOUT", "20"))

# Ordered so a "min severity" gate is a simple >= compare.
SEVERITY_RANK = {"Unknown": 0, "Minor": 1, "Moderate": 2, "Severe": 3, "Extreme": 4}

# Non-Weather Emergency Messages relayed by NWS. These ALWAYS pass the severity
# gate -- an AMBER alert or evacuation order is never filtered out for being
# tagged low/unknown severity. Matched case-insensitively against event text.
NWEM_EVENTS = {
    "child abduction emergency", "amber alert",
    "civil emergency message", "civil danger warning",
    "law enforcement warning", "local area emergency",
    "911 telephone outage emergency",
    "evacuation immediate", "evacuation - immediate",
    "shelter in place warning",
    "hazardous materials warning", "radiological hazard warning",
    "nuclear power plant warning", "fire warning",
}


def _get_json(url, timeout=HTTP_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": NWS_UA, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def geocode(q):
    """Place text -> {lat, lon, label} or None (via local Nominatim, US-biased)."""
    qs = urllib.parse.urlencode({"q": q, "format": "json", "limit": "1", "countrycodes": "us"})
    try:
        rows = _get_json(f"{NOMINATIM_URL}/search?{qs}")
    except Exception:
        return None
    if not rows:
        return None
    r = rows[0]
    return {"lat": round(float(r["lat"]), 4), "lon": round(float(r["lon"]), 4),
            "label": r.get("display_name", q)}


def active_for_point(lat, lon):
    """Active alerts affecting a point. NWS does the geo intersection server-side,
    so a single call returns exactly the alerts in force at that coordinate.
    Returns a list of normalized alert dicts (may be empty); None on fetch error."""
    url = f"{NWS_URL}/alerts/active?point={round(float(lat),4)},{round(float(lon),4)}"
    try:
        data = _get_json(url)
    except Exception:
        return None
    out = []
    for f in data.get("features", []):
        p = f.get("properties", {}) or {}
        out.append({
            "id": p.get("id") or f.get("id"),
            "event": p.get("event") or "Alert",
            "headline": p.get("headline") or p.get("event") or "Alert",
            "severity": p.get("severity") or "Unknown",
            "certainty": p.get("certainty") or "",
            "urgency": p.get("urgency") or "",
            "msg_type": p.get("messageType") or "Alert",   # Alert / Update / Cancel
            "sent": p.get("sent") or "",
            "effective": p.get("effective") or "",
            "expires": p.get("expires") or "",
            "area": p.get("areaDesc") or "",
            "description": (p.get("description") or "").strip(),
            "instruction": (p.get("instruction") or "").strip(),
        })
    return out


def passes(alert, min_severity):
    """True if this alert should be delivered under a subscriber's min-severity
    (NWEM events always pass). Cancels always pass so a subscriber learns the
    all-clear."""
    if (alert.get("msg_type") or "").lower() == "cancel":
        return True
    if (alert.get("event") or "").strip().lower() in NWEM_EVENTS:
        return True
    have = SEVERITY_RANK.get(alert.get("severity") or "Unknown", 0)
    want = SEVERITY_RANK.get(min_severity or "Severe", 3)
    return have >= want


def health():
    nom = nws = False
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{NOMINATIM_URL}/search?q=test&format=json&limit=1",
            headers={"User-Agent": NWS_UA}), timeout=8)
        nom = True
    except Exception:
        pass
    try:
        _get_json(f"{NWS_URL}/alerts/active?point=38.9,-77.0", timeout=10)
        nws = True
    except Exception:
        pass
    return {"nominatim": nom, "nws": nws}
