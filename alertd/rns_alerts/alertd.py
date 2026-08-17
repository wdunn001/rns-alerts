"""rns-alerts daemon: an LXMF endpoint that takes plain-language subscribe
commands and PUSHES matching NWS/emergency alerts to subscribers, plus a poll
loop that also writes MeshData-tagged pages for the nomadnet-alerts browse node.

Standalone RNS instance (own identity/config), same rationale as the meshtastic
bridge: a service with its own LXMF identity must not ride an rnsd shared-instance
socket. RNS.Reticulum() runs on the main thread (installs signal handlers)."""
import hashlib
import os
import threading
import time

import RNS
import LXMF

from . import commands, config, nws, render, store


class S:
    reticulum = None
    identity = None
    router = None
    delivery = None
    lxmf_address = None
    ready = False
    error = None
    last_poll_ts = None
    last_poll_pushed = 0
    active_count = 0
    inbound_count = 0
    pushed_total = 0


def _page_id(alert_id):
    return hashlib.md5((alert_id or "").encode()).hexdigest()[:16]


def send_lxmf(dest_hash, text, title="Alert"):
    """Deliver one LXMF message. Direct if the recipient's identity is known
    (a subscriber just messaged us, so it is), else propagated via the pinned
    propagation node when one is configured."""
    if not S.ready:
        return False
    ident = RNS.Identity.recall(dest_hash)
    if ident is None:
        RNS.Transport.request_path(dest_hash)
        return False
    dest = RNS.Destination(ident, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
    pn = S.router.get_outbound_propagation_node() if S.router else None
    method = LXMF.LXMessage.DIRECT if (RNS.Transport.has_path(dest_hash) or pn is None) else LXMF.LXMessage.PROPAGATED
    msg = LXMF.LXMessage(dest, S.delivery, text, title, desired_method=method)
    S.router.handle_outbound(msg)
    S.pushed_total += 1
    return True


def _on_lxmf(message):
    """Inbound command from a subscriber -> handle + reply."""
    S.inbound_count += 1
    try:
        text = message.content.decode("utf-8", "replace") if message.content else ""
    except Exception:
        text = ""
    src = RNS.hexrep(message.source_hash, delimit=False)
    try:
        reply = commands.handle(src, text)
    except Exception as e:  # noqa: BLE001
        reply = f"Sorry, that didn't work: {e}"
        RNS.log(f"rns-alerts: command error from {src}: {e}", RNS.LOG_ERROR)
    RNS.log(f"rns-alerts: cmd from {src}: {text[:60]!r}", RNS.LOG_NOTICE)
    send_lxmf(message.source_hash, reply, "Quasarke Alerts")


def _write_pages(active):
    """active = list of (alert, place, page_id). Writes per-alert MeshData pages
    + the browse index into the shared pages volume for nomadnet-alerts."""
    try:
        base = config.PAGES_DIR
        adir = os.path.join(base, "a")
        os.makedirs(adir, exist_ok=True)
        live_ids = set()
        for alert, place, pid in active:
            live_ids.add(pid)
            p = os.path.join(adir, pid + ".mu")
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(render.alert_page(alert, place))
            os.replace(tmp, p)
        # prune pages for alerts no longer active
        for fn in os.listdir(adir):
            if fn.endswith(".mu") and fn[:-3] not in live_ids:
                try:
                    os.remove(os.path.join(adir, fn))
                except Exception:
                    pass
        idx = os.path.join(base, "index.mu")
        tmp = idx + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(render.index_page(active))
        os.replace(tmp, idx)
    except Exception as e:  # noqa: BLE001
        RNS.log(f"rns-alerts: page write error: {e}", RNS.LOG_ERROR)


def poll_once():
    pushed = 0
    active = []            # (alert, place, page_id) for the browse index
    seen_pages = set()
    for lat, lon in store.distinct_points():
        alerts = nws.active_for_point(lat, lon)
        if alerts is None:                       # fetch error -> skip this point this cycle
            continue
        subs = store.subs_at(lat, lon)
        place = subs[0]["place"] if subs else f"{lat},{lon}"
        for alert in alerts:
            aid, mt = alert.get("id"), alert.get("msg_type", "Alert")
            if not aid:
                continue
            pid = _page_id(aid)
            if pid not in seen_pages:
                seen_pages.add(pid)
                active.append((alert, place, pid))
            for sub in subs:
                if not nws.passes(alert, sub["min_severity"]):
                    continue
                if store.already_sent(sub["lxmf_hex"], aid, mt):
                    continue
                if send_lxmf(bytes.fromhex(sub["lxmf_hex"]),
                             render.format_push(alert, sub["place"]),
                             "⚠ " + alert.get("event", "Alert")):
                    store.mark_sent(sub["lxmf_hex"], aid, mt)
                    pushed += 1
    _write_pages(active)
    S.last_poll_ts = time.time()
    S.last_poll_pushed = pushed
    S.active_count = len(active)
    S.pushed_total += 0
    return pushed


def run():
    store.init()
    os.makedirs(config.RNS_CONFIG_DIR, exist_ok=True)
    try:
        S.reticulum = RNS.Reticulum(configdir=config.RNS_CONFIG_DIR)
    except Exception as e:  # noqa: BLE001
        S.error = f"Reticulum init failed: {e}"
        RNS.log(f"rns-alerts: {S.error}", RNS.LOG_ERROR)
        return

    os.makedirs(os.path.dirname(config.IDENTITY_PATH), exist_ok=True)
    if os.path.isfile(config.IDENTITY_PATH):
        S.identity = RNS.Identity.from_file(config.IDENTITY_PATH)
    else:
        S.identity = RNS.Identity()
        S.identity.to_file(config.IDENTITY_PATH)

    os.makedirs(config.STORAGE_DIR, exist_ok=True)
    S.router = LXMF.LXMRouter(identity=S.identity, storagepath=config.STORAGE_DIR)
    S.delivery = S.router.register_delivery_identity(S.identity, display_name=config.DISPLAY_NAME)
    S.router.register_delivery_callback(_on_lxmf)
    S.lxmf_address = RNS.hexrep(S.delivery.hash, delimit=False)
    if config.PROPAGATION_NODE_HASH:
        try:
            S.router.set_outbound_propagation_node(bytes.fromhex(config.PROPAGATION_NODE_HASH))
        except Exception as e:  # noqa: BLE001
            RNS.log(f"rns-alerts: bad PROPAGATION_NODE_HASH: {e}", RNS.LOG_ERROR)

    S.delivery.announce()
    S.ready = True
    RNS.log(f"rns-alerts: ready, LXMF address {S.lxmf_address}", RNS.LOG_NOTICE)

    last_announce = last_prune = 0
    while True:
        try:
            poll_once()
        except Exception as e:  # noqa: BLE001
            RNS.log(f"rns-alerts: poll error: {e}", RNS.LOG_ERROR)
        now = time.time()
        if now - last_announce > 1800:          # re-announce the endpoint every 30 min
            try:
                S.delivery.announce()
            except Exception:
                pass
            last_announce = now
        if now - last_prune > 86400:
            try:
                store.prune_ledger()
            except Exception:
                pass
            last_prune = now
        time.sleep(config.POLL_INTERVAL)
