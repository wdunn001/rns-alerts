"""Render alerts two ways: as the plain-text LXMF push a subscriber receives,
and as MeshData-tagged micron pages the nomadnet-alerts node serves (so Beacon
indexes active alerts and they turn up in mesh search)."""
import re

_SEV_MARK = {"Extreme": "!!!", "Severe": "!!", "Moderate": "!", "Minor": "", "Unknown": ""}


def _clip(s, n):
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def format_push(alert, place):
    """The LXMF message body a subscriber gets. Kept compact for LoRa."""
    mark = _SEV_MARK.get(alert.get("severity", ""), "")
    cancel = (alert.get("msg_type") or "").lower() == "cancel"
    head = ("CLEARED: " if cancel else (mark + " " if mark else "")) + (alert.get("event") or "Alert")
    lines = [head.strip(), f"[{place}]"]
    if alert.get("severity"):
        meta = alert["severity"]
        if alert.get("urgency"):
            meta += " · " + alert["urgency"]
        lines.append(meta)
    if alert.get("area"):
        lines.append(_clip(alert["area"], 160))
    body = _clip(alert.get("description", ""), 700)
    if body and not cancel:
        lines.append("")
        lines.append(body)
    if alert.get("instruction") and not cancel:
        lines.append("")
        lines.append("What to do: " + _clip(alert["instruction"], 400))
    if alert.get("expires"):
        lines.append("")
        lines.append("Expires: " + alert["expires"].replace("T", " ")[:16])
    return "\n".join(lines)


def esc(s):
    return str(s).replace("\\", "\\\\").replace("`", "'")


def alert_page(alert, place):
    """A single active alert as a MeshData-tagged static micron page."""
    sev = alert.get("severity", "Unknown")
    head = [
        "# +meshdata: 0.1",
        "# +type: alert",
        "# +title: " + esc(alert.get("event", "Alert")) + " - " + esc(place),
        "# +description: " + esc(_clip(alert.get("headline") or alert.get("event"), 280)),
        "# +tags: alert, emergency, weather, " + esc(sev) + ", " + esc(place),
        "# +lang: en",
    ]
    if alert.get("effective"):
        head.append("# +date: " + esc(alert["effective"][:16].replace("T", " ")))
    body = ["`c`F900" + esc(alert.get("event", "Alert")) + "`f`a",
            "`c`F888" + esc(place) + "  ·  " + esc(sev) + "`f`a", "-"]
    if alert.get("area"):
        body.append("`F888Area:`f " + esc(alert["area"]))
    if alert.get("expires"):
        body.append("`F888Expires:`f " + esc(alert["expires"].replace("T", " ")[:16]))
    body.append("")
    for para in re.split(r"\n{2,}", (alert.get("description") or "").strip()):
        if para.strip():
            body.append(esc(para.strip()))
            body.append("")
    if alert.get("instruction"):
        body.append("`F888What to do:`f " + esc(alert["instruction"]))
        body.append("")
    body.append("`[< all active alerts`:/page/index.mu]")
    return "\n".join(head) + "\n" + "\n".join(body) + "\n"


def index_page(active):
    """Browse list of currently-active alerts (newest/most-severe first). Static;
    regenerated each poll. `active` = list of (alert, place, page_id)."""
    from .nws import SEVERITY_RANK
    active = sorted(active, key=lambda ap: SEVERITY_RANK.get(ap[0].get("severity", "Unknown"), 0),
                    reverse=True)
    head = [
        "# +meshdata: 0.1",
        "# +type: index",
        "# +title: Active alerts",
        "# +description: Live NWS + emergency alerts across subscribed areas ("
        + str(len(active)) + " active)",
        "# +tags: alert, emergency, weather",
        "# +lang: en",
    ]
    body = ["`c`F900⚠ Active alerts`f`a",
            "`c`F888NWS watches/warnings + AMBER/civil alerts over Reticulum`f`a", "-"]
    if not active:
        body.append("`F888No active alerts in subscribed areas right now.`f")
    else:
        for alert, place, pid in active:
            sev = alert.get("severity", "")
            body.append("`[" + esc(alert.get("event", "Alert")) + " - " + esc(place)
                        + "`:/page/a/" + esc(pid) + ".mu]")
            bits = [b for b in (sev, alert.get("area", ""),
                    (("expires " + alert["expires"][:16].replace("T", " ")) if alert.get("expires") else ""))
                    if b]
            body.append("  `F888" + esc("  ·  ".join(bits)) + "`f")
            body.append("")
    body.append("-")
    body.append("`F666Subscribe for push alerts: message the alerts node 'subscribe <place>'.`f")
    return "\n".join(head) + "\n" + "\n".join(body) + "\n"
