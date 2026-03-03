"""Configuration loaded from environment."""

import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _strip_value(s: str) -> str:
    """Strip whitespace and inline # comment from env value (e.g. 'true  # comment' -> 'true')."""
    if not s:
        return ""
    if "#" in s:
        s = s.split("#", 1)[0]
    return s.strip()


def _bool(s: str) -> bool:
    if not s:
        return True
    return _strip_value(s).lower() in ("1", "true", "yes", "on")


def get_config():
    server = _strip_value(os.environ.get("VCENTER_SERVER", ""))
    if not server:
        raise ValueError("VCENTER_SERVER must be set (e.g. https://vcenter.example.com)")
    # Ensure scheme
    if not server.startswith("http://") and not server.startswith("https://"):
        server = "https://" + server
    user = _strip_value(os.environ.get("VCENTER_USER", "")) or "administrator@vsphere.local"
    password = _strip_value(os.environ.get("VCENTER_PASSWORD", ""))
    if not password:
        raise ValueError("VCENTER_PASSWORD must be set")
    verify_ssl = _bool(os.environ.get("VCENTER_VERIFY_SSL", "true"))
    host = _strip_value(os.environ.get("EXPORTER_HOST", "0.0.0.0")) or "0.0.0.0"
    port = int(_strip_value(os.environ.get("EXPORTER_PORT", "9680")) or "9680")
    scrape_interval = int(_strip_value(os.environ.get("SCRAPE_INTERVAL", "300")) or "300")
    # Logging
    log_file = _strip_value(os.environ.get("LOG_FILE", ""))
    log_level = _strip_value(os.environ.get("LOG_LEVEL", "INFO")).upper()
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
        perf_timeout_sec = int(_strip_value(os.environ.get("VCENTER_PERF_TIMEOUT_SEC", "0")) or "0")
    except ValueError:
        perf_timeout_sec = 0
    try:
        perf_max_hosts = int(_strip_value(os.environ.get("VCENTER_PERF_MAX_HOSTS", "0")) or "0")
    except ValueError:
        perf_max_hosts = 0
    try:
        perf_max_vms = int(_strip_value(os.environ.get("VCENTER_PERF_MAX_VMS", "0")) or "0")
    except ValueError:
        perf_max_vms = 0
    # Async perf: collect in background thread, serve from cache (avoids scrape timeout)
    perf_async = _bool(os.environ.get("VCENTER_PERF_ASYNC", "false"))
    try:
        perf_interval_sec = int(_strip_value(os.environ.get("VCENTER_PERF_INTERVAL_SEC", "300")) or "300")
    except ValueError:
        perf_interval_sec = 300
    # vSAN health (cluster score + host status)
    collect_vsan = _bool(os.environ.get("VCENTER_COLLECT_VSAN", "true"))
    vsan_async = _bool(os.environ.get("VCENTER_VSAN_ASYNC", "true"))
    try:
        vsan_interval_sec = int(_strip_value(os.environ.get("VCENTER_VSAN_INTERVAL_SEC", "300")) or "300")
    except ValueError:
        vsan_interval_sec = 300
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
        "collect_vsan": collect_vsan,
        "vsan_async": vsan_async,
        "vsan_interval_sec": max(60, vsan_interval_sec),
    }
