"""Entrypoint: a tiny healthz HTTP surface in a background thread, then the
alert daemon on the main thread (RNS needs the main thread for signal handlers)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import alertd, config, store


class _Health(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        # /active?lat=&lon= -> banner-worthy alerts for a point (the Beacon page
        # calls this for an opted-in user's location; pull, not push).
        if self.path.startswith("/active"):
            qs = parse_qs(urlparse(self.path).query)
            out = []
            try:
                lat = float(qs.get("lat", [""])[0])
                lon = float(qs.get("lon", [""])[0])
                for a in alertd.active_worthy(lat, lon):
                    out.append({"event": a.get("event"), "severity": a.get("severity"),
                                "headline": a.get("headline"), "area": a.get("area"),
                                "expires": a.get("expires")})
            except Exception:
                out = []
            body = json.dumps({"alerts": out}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        # /subscribed?rid=<identity hash> -> is this identity subscribed to push?
        if self.path.startswith("/subscribed"):
            qs = parse_qs(urlparse(self.path).query)
            body = json.dumps(alertd.subscription_status(qs.get("rid", [""])[0])).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            nsubs = len(store.all_subs())
        except Exception:
            nsubs = None
        ok = alertd.S.ready
        body = json.dumps({
            "status": "ok" if ok else "starting",
            "rns_ready": alertd.S.ready,
            "lxmf_address": alertd.S.lxmf_address,
            "subscriptions": nsubs,
            "active_alerts": alertd.S.active_count,
            "last_poll_pushed": alertd.S.last_poll_pushed,
            "pushed_total": alertd.S.pushed_total,
            "inbound_count": alertd.S.inbound_count,
        }).encode()
        self.send_response(200 if ok else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # push opt-in from the Beacon account page: /subscribe + /unsubscribe by
        # RNS identity hash (the account page has the hash; we derive the LXMF dest).
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}") if 0 < n <= 65536 else {}
        except Exception:
            body = {}
        rid = (body.get("rid") or "").strip()
        if self.path.startswith("/unsubscribe"):
            out = alertd.unsubscribe_by_identity(rid)
        elif self.path.startswith("/subscribe"):
            out = alertd.subscribe_by_identity(rid, body.get("lat"), body.get("lon"),
                                               body.get("place") or "your area",
                                               body.get("min_severity") or "Severe")
        else:
            out = {"ok": False, "err": "unknown op"}
        data = json.dumps(out).encode()
        self.send_response(200 if out.get("ok") else 400)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)


def _serve_health():
    HTTPServer(("0.0.0.0", config.HEALTH_PORT), _Health).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=_serve_health, daemon=True, name="health").start()
    alertd.run()
