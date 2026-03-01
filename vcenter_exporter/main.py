"""
vCenter Prometheus Exporter - HTTP server exposing /metrics.

Usage:
  Set env vars (or .env): VCENTER_SERVER, VCENTER_USER, VCENTER_PASSWORD.
  Run: python -m vcenter_exporter.main
  Or: vcenter-exporter   (if installed as console script)
"""

import logging
import sys

from prometheus_client import start_http_server

from .config import get_config
from .vcenter_client import VCenterClient
from .collector import VCenterCollector
from prometheus_client import REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        config = get_config()
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    client = VCenterClient(
        server=config["vcenter_server"],
        user=config["vcenter_user"],
        password=config["vcenter_password"],
        verify_ssl=config["vcenter_verify_ssl"],
    )
    collector = VCenterCollector(client, vcenter_instance=config["vcenter_instance"])
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
