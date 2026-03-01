"""Configuration loaded from environment."""

import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _bool(s: str) -> bool:
    if not s:
        return True
    return s.strip().lower() in ("1", "true", "yes", "on")


def get_config():
    server = os.environ.get("VCENTER_SERVER", "").strip()
    if not server:
        raise ValueError("VCENTER_SERVER must be set (e.g. https://vcenter.example.com)")
    # Ensure scheme
    if not server.startswith("http://") and not server.startswith("https://"):
        server = "https://" + server
    user = os.environ.get("VCENTER_USER", "").strip() or "administrator@vsphere.local"
    password = os.environ.get("VCENTER_PASSWORD", "").strip()
    if not password:
        raise ValueError("VCENTER_PASSWORD must be set")
    verify_ssl = _bool(os.environ.get("VCENTER_VERIFY_SSL", "true"))
    host = os.environ.get("EXPORTER_HOST", "0.0.0.0").strip()
    port = int(os.environ.get("EXPORTER_PORT", "9680").strip() or "9680")
    scrape_interval = int(os.environ.get("SCRAPE_INTERVAL", "300").strip() or "300")
    # Instance label: hostname from server URL
    try:
        parsed = urlparse(server)
        vcenter_instance = parsed.hostname or "default"
    except Exception:
        vcenter_instance = "default"
    return {
        "vcenter_server": server,
        "vcenter_user": user,
        "vcenter_password": password,
        "vcenter_verify_ssl": verify_ssl,
        "exporter_host": host,
        "exporter_port": port,
        "scrape_interval": scrape_interval,
        "vcenter_instance": vcenter_instance,
    }
