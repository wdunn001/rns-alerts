"""Parse an inbound LXMF message into an action and produce the reply text.
Subscribing is a plain-language command so it works from any LXMF client
(Sideband, MeshChat, NomadNet) with no forms."""
from . import nws, store

HELP = (
    "Quasarke Alerts - NWS watches/warnings + AMBER/civil/evacuation alerts over "
    "Reticulum. Send me:\n"
    "  subscribe <place>   e.g. 'subscribe Boulder CO' or 'subscribe 80301'\n"
    "  severe|moderate|minor <place>   set minimum severity (default: severe)\n"
    "  list                your current subscriptions\n"
    "  unsubscribe         stop all alerts\n"
    "  help                this message\n"
    "AMBER + civil/evacuation/shelter alerts always come through regardless of "
    "the severity setting."
)

_SEV = {"extreme": "Extreme", "severe": "Severe", "moderate": "Moderate",
        "minor": "Minor", "all": "Minor"}


def handle(lxmf_hex, text):
    words = (text or "").strip().split()
    if not words:
        return HELP
    verb = words[0].lower()

    if verb in ("help", "?", "commands", "start", "info"):
        return HELP
    if verb in ("unsubscribe", "unsub", "stop", "off", "cancel", "remove"):
        n = store.remove_subs(lxmf_hex)
        return (f"Unsubscribed - removed {n} subscription(s). No more alerts."
                if n else "You had no subscriptions.")
    if verb in ("list", "status", "mine", "subs", "subscriptions"):
        subs = store.list_subs(lxmf_hex)
        if not subs:
            return "No subscriptions yet. Send 'subscribe <place>' to start."
        return "Your alert subscriptions:\n" + "\n".join(
            f"  - {s['place']}  (>= {s['min_severity']})" for s in subs)

    # subscribe flow: strip a leading verb and/or a leading severity word.
    rest = words[1:] if verb in ("subscribe", "sub", "watch", "alerts", "alert") else words
    min_sev = "Severe"
    if verb in _SEV:
        min_sev, rest = _SEV[verb], words[1:]
    if rest and rest[0].lower() in _SEV:
        min_sev, rest = _SEV[rest[0].lower()], rest[1:]

    place = " ".join(rest).strip()
    if not place:
        return "Tell me a place, e.g. 'subscribe Boulder CO' or 'subscribe 80301'.\n\n" + HELP
    g = nws.geocode(place)
    if not g:
        return f"Couldn't find '{place}'. Try a US city + state, or a ZIP code."
    store.add_sub(lxmf_hex, g["lat"], g["lon"], place, min_sev)
    return (f"Subscribed to alerts for {place} (>= {min_sev}).\n"
            f"({g['label']})\n"
            "You'll get NWS warnings + AMBER/civil alerts here. Send 'unsubscribe' to stop.")
