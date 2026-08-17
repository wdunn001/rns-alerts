"""Entrypoint: a tiny healthz HTTP surface in a background thread, then the
alert daemon on the main thread (RNS needs the main thread for signal handlers)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import alertd, config, store


class _Health(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
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


def _serve_health():
    HTTPServer(("0.0.0.0", config.HEALTH_PORT), _Health).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=_serve_health, daemon=True, name="health").start()
    alertd.run()
