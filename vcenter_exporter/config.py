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
    # Logging
    log_file = os.environ.get("LOG_FILE", "").strip()
    log_level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        log_level = "INFO"
    # Instance label: hostname from server URL
    try:
        parsed = urlparse(server)
        vcenter_instance = parsed.hostname or "default"
    except Exception:
        vcenter_instance = "default"
    # Performance collection (can cause long scrapes / timeouts)
    collect_perf = _bool(os.environ.get("VCENTER_COLLECT_PERF", "true"))
    try:
        perf_timeout_sec = int(os.environ.get("VCENTER_PERF_TIMEOUT_SEC", "0").strip() or "0")
    except ValueError:
        perf_timeout_sec = 0
    try:
        perf_max_hosts = int(os.environ.get("VCENTER_PERF_MAX_HOSTS", "0").strip() or "0")
    except ValueError:
        perf_max_hosts = 0
    try:
        perf_max_vms = int(os.environ.get("VCENTER_PERF_MAX_VMS", "0").strip() or "0")
    except ValueError:
        perf_max_vms = 0
    # Async perf: collect in background thread, serve from cache (avoids scrape timeout)
    perf_async = _bool(os.environ.get("VCENTER_PERF_ASYNC", "false"))
    try:
        perf_interval_sec = int(os.environ.get("VCENTER_PERF_INTERVAL_SEC", "300").strip() or "300")
    except ValueError:
        perf_interval_sec = 300
    return {
        "vcenter_server": server,
        "vcenter_user": user,
        "vcenter_password": password,
        "vcenter_verify_ssl": verify_ssl,
        "exporter_host": host,
        "exporter_port": port,
        "scrape_interval": scrape_interval,
        "log_file": log_file,
        "log_level": log_level,
        "vcenter_instance": vcenter_instance,
        "collect_perf": collect_perf,
        "perf_timeout_sec": max(0, perf_timeout_sec),
        "perf_max_hosts": max(0, perf_max_hosts),
        "perf_max_vms": max(0, perf_max_vms),
        "perf_async": perf_async,
        "perf_interval_sec": max(10, perf_interval_sec),
    }
