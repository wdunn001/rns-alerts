"""Env-driven config for rns-alerts (see docker-compose.yml)."""
import os

POLL_INTERVAL = int(os.environ.get("ALERTS_POLL_INTERVAL", "120"))
RNS_CONFIG_DIR = os.environ.get("RNS_CONFIG_DIR", "/config/rns")
STORAGE_DIR = os.environ.get("STORAGE_DIR", "/config")
IDENTITY_PATH = os.environ.get("IDENTITY_PATH", "/config/identity/alerts_identity")
PAGES_DIR = os.environ.get("ALERTS_PAGES_DIR", "/data/pages")
DISPLAY_NAME = os.environ.get("DISPLAY_NAME", "Quasarke Alerts")
PROPAGATION_NODE_HASH = os.environ.get("PROPAGATION_NODE_HASH", "").strip()
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8222"))
