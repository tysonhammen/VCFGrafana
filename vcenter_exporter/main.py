"""
vCenter Prometheus Exporter - HTTP server exposing /metrics.

Usage:
  Set env vars (or .env): VCENTER_SERVER, VCENTER_USER, VCENTER_PASSWORD.
  Run: python -m vcenter_exporter.main
  Or: vcenter-exporter   (if installed as console script)
"""

import logging
import os
import sys

from prometheus_client import start_http_server

from .config import get_config
from .vcenter_client import VCenterClient
from .collector import VCenterCollector
from prometheus_client import REGISTRY


def setup_logging(config: dict) -> None:
    """Configure logging: console and optional log file at level from config."""
    log_level = getattr(logging, config.get("log_level", "INFO"), logging.INFO)
    log_file = config.get("log_file", "").strip()
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    root = logging.getLogger()
    root.setLevel(log_level)
    for h in root.handlers[:]:
        root.removeHandler(h)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    console.setFormatter(logging.Formatter(fmt))
    root.addHandler(console)
    if log_file:
        try:
            path = os.path.abspath(log_file)
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            fh = logging.FileHandler(path, encoding="utf-8")
            fh.setLevel(log_level)
            fh.setFormatter(logging.Formatter(fmt))
            root.addHandler(fh)
            logging.getLogger("vcenter_exporter").info("Logging to file: %s", path)
        except OSError as e:
            msg = "Could not open log file %s: %s" % (log_file, e)
            logging.getLogger("vcenter_exporter").warning(msg)
            print(msg, file=sys.stderr)
    else:
        logging.getLogger("vcenter_exporter").info("LOG_FILE not set; logging to stdout only")


def main() -> None:
    try:
        config = get_config()
    except ValueError as e:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        logging.getLogger(__name__).error("Configuration error: %s", e)
        sys.exit(1)

    setup_logging(config)
    logger = logging.getLogger(__name__)

    client = VCenterClient(
        server=config["vcenter_server"],
        user=config["vcenter_user"],
        password=config["vcenter_password"],
        verify_ssl=config["vcenter_verify_ssl"],
    )
    collector = VCenterCollector(
        client,
        vcenter_instance=config["vcenter_instance"],
        collect_perf=config["collect_perf"],
        perf_timeout_sec=config["perf_timeout_sec"],
        perf_max_hosts=config["perf_max_hosts"],
        perf_max_vms=config["perf_max_vms"],
        perf_async=config["perf_async"],
        perf_interval_sec=config["perf_interval_sec"],
        collect_vsan=config["collect_vsan"],
        vsan_async=config["vsan_async"],
        vsan_interval_sec=config["vsan_interval_sec"],
    )
    REGISTRY.register(collector)

    host = config["exporter_host"]
    port = config["exporter_port"]
    logger.info(
        "Starting vCenter exporter on %s:%s (vCenter: %s)",
        host,
        port,
        config["vcenter_server"],
    )
    start_http_server(port=port, addr=host)
    logger.info("Metrics available at http://%s:%s/metrics", host, port)

    try:
        while True:
            import time
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down")
        client.close()


if __name__ == "__main__":
    main()
