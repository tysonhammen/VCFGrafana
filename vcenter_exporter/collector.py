"""
Prometheus collector that fetches vCenter inventory and performance metrics.

Exposes:
- vcenter_cluster_* (clusters)
- vcenter_host_* (hosts)
- vcenter_datastore_* (storage)
- vcenter_vm_* (VMs)
- vcenter_perf_* (host and VM performance from vStats when available)
"""

import logging
import time
from typing import Any, Optional

from prometheus_client.core import GaugeMetricFamily, REGISTRY

from .vcenter_client import VCenterClient, VCenterAPIError
from . import perf_manager

logger = logging.getLogger(__name__)

# vStats metric names to collect (subset; API may return different names)
VSTATS_METRICS_HOST = ["cpu.usage", "mem.usage", "cpu.util"]
VSTATS_METRICS_VM = ["cpu.usage", "mem.usage", "cpu.util"]


def _log_perf_failure(step: str, e: "VCenterAPIError") -> None:
    """Log performance collection failure with a clear cause."""
    code = e.status_code or 0
    if code == 401:
        logger.info(
            "vStats %s not available (HTTP 401 Unauthorized). "
            "REST session for /api/stats/* may be missing or expired; check logs for 'REST session'.",
            step,
        )
    elif code == 404:
        logger.info(
            "vStats %s not available (HTTP 404). "
            "Stats API may not be enabled on this vCenter or version.",
            step,
        )
    elif code == 400:
        logger.info(
            "vStats %s not available (HTTP 400 Bad Request). "
            "Request parameters may be unsupported by this vCenter.",
            step,
        )
    else:
        logger.info("vStats %s not available (HTTP %s), skipping performance.", step, code)
    logger.debug("vStats %s error: %s", step, (e.response_text or str(e))[:500])


class VCenterCollector:
    """
    Prometheus collector that queries vCenter REST API and exposes
    clusters, hosts, datastores, and VMs as metrics.
    """

    def __init__(self, client: VCenterClient, vcenter_instance: str = ""):
        self.client = client
        self.vcenter_instance = vcenter_instance or "default"

    def collect(self):
        """Yield Prometheus metrics from vCenter."""
        try:
            yield from self._collect_clusters()
            yield from self._collect_hosts()
            yield from self._collect_datastores()
            yield from self._collect_vms()
            yield from self._collect_performance()
            # Signal successful scrape
            err = GaugeMetricFamily(
                "vcenter_scrape_error",
                "1 if the last scrape of vCenter failed, 0 on success",
                labels=["vcenter"],
            )
            err.add_metric([self.vcenter_instance], 0.0)
            yield err
        except VCenterAPIError as e:
            logger.exception("vCenter API error during collect: %s", e)
            # Expose a failure metric so Prometheus can alert
            err = GaugeMetricFamily(
                "vcenter_scrape_error",
                "1 if the last scrape of vCenter failed",
                labels=["vcenter"],
            )
            err.add_metric([self.vcenter_instance], 1.0)
            yield err

    def _label(self, labels: dict) -> tuple:
        """Build label names and values including vcenter instance (for reuse if needed)."""
        base = ["vcenter"]
        values = [self.vcenter_instance]
        for k, v in sorted(labels.items()):
            base.append(k)
            values.append(str(v) if v is not None else "")
        return base, values

    def _collect_clusters(self):
        """Cluster metrics."""
        clusters = self.client.list_clusters()
        name_labels, _ = self._label({"name": None})
        cluster_info = GaugeMetricFamily(
            "vcenter_cluster_info",
            "vCenter cluster information (1 per cluster)",
            labels=name_labels,
        )
        cluster_count = GaugeMetricFamily(
            "vcenter_cluster_total",
            "Total number of clusters",
            labels=["vcenter"],
        )
        for c in clusters:
            name = c.get("name") or c.get("cluster", "unknown")
            cluster_info.add_metric([self.vcenter_instance, name], 1.0)
        cluster_count.add_metric([self.vcenter_instance], len(clusters))
        yield cluster_info
        yield cluster_count

    def _collect_hosts(self):
        """Host metrics."""
        hosts = self.client.list_hosts()
        labels = ["vcenter", "host_id", "name", "connection_state", "power_state", "cluster"]
        host_info = GaugeMetricFamily(
            "vcenter_host_info",
            "vCenter host information (1 per host)",
            labels=labels,
        )
        host_count = GaugeMetricFamily(
            "vcenter_host_total",
            "Total number of hosts",
            labels=["vcenter"],
        )
        for h in hosts:
            host_id = h.get("host", "unknown")
            name = h.get("name") or host_id
            conn = h.get("connection_state", "UNKNOWN")
            power = h.get("power_state", "UNKNOWN")
            cluster = h.get("cluster", "") or ""
            host_info.add_metric(
                [self.vcenter_instance, host_id, name, conn, power, cluster], 1.0
            )
        host_count.add_metric([self.vcenter_instance], len(hosts))
        yield host_info
        yield host_count

    def _collect_datastores(self):
        """Datastore (storage) metrics."""
        datastores = self.client.list_datastores()
        labels = ["vcenter", "datastore_id", "name", "type"]
        ds_info = GaugeMetricFamily(
            "vcenter_datastore_info",
            "vCenter datastore information (1 per datastore)",
            labels=labels,
        )
        ds_capacity = GaugeMetricFamily(
            "vcenter_datastore_capacity_bytes",
            "Datastore capacity in bytes",
            labels=["vcenter", "datastore_id", "name"],
        )
        ds_free = GaugeMetricFamily(
            "vcenter_datastore_free_bytes",
            "Datastore free space in bytes",
            labels=["vcenter", "datastore_id", "name"],
        )
        ds_count = GaugeMetricFamily(
            "vcenter_datastore_total",
            "Total number of datastores",
            labels=["vcenter"],
        )
        for d in datastores:
            ds_id = d.get("datastore", "unknown")
            name = d.get("name") or ds_id
            ds_type = d.get("type", "UNKNOWN")
            ds_info.add_metric([self.vcenter_instance, ds_id, name, ds_type], 1.0)
            # Capacity/free may be in different units in API; common is bytes
            cap = d.get("capacity") or 0
            free = d.get("free_space") or d.get("freeSpace") or 0
            ds_capacity.add_metric([self.vcenter_instance, ds_id, name], cap)
            ds_free.add_metric([self.vcenter_instance, ds_id, name], free)
        ds_count.add_metric([self.vcenter_instance], len(datastores))
        yield ds_info
        yield ds_capacity
        yield ds_free
        yield ds_count

    def _collect_vms(self):
        """VM metrics."""
        vms = self.client.list_vms()
        labels = [
            "vcenter", "vm_id", "name", "power_state", "guest_os", "cluster", "host"
        ]
        vm_info = GaugeMetricFamily(
            "vcenter_vm_info",
            "vCenter VM information (1 per VM)",
            labels=labels,
        )
        vm_cpu = GaugeMetricFamily(
            "vcenter_vm_cpu_count",
            "Number of CPUs configured for the VM",
            labels=["vcenter", "vm_id", "name"],
        )
        vm_memory_mib = GaugeMetricFamily(
            "vcenter_vm_memory_mib",
            "Configured memory size in MiB",
            labels=["vcenter", "vm_id", "name"],
        )
        vm_count = GaugeMetricFamily(
            "vcenter_vm_total",
            "Total number of VMs",
            labels=["vcenter"],
        )
        for v in vms:
            vm_id = v.get("vm", "unknown")
            name = v.get("name") or vm_id
            power = v.get("power_state", "UNKNOWN")
            guest_os = v.get("guest_OS", "") or ""
            cluster = v.get("cluster", "") or ""
            host = v.get("host", "") or ""
            vm_info.add_metric(
                [self.vcenter_instance, vm_id, name, power, guest_os, cluster, host], 1.0
            )
            cpu = v.get("cpu_count") or v.get("cpu", 0)
            mem = v.get("memory_size_MiB") or v.get("memory_size_MIB") or 0
            vm_cpu.add_metric([self.vcenter_instance, vm_id, name], cpu)
            vm_memory_mib.add_metric([self.vcenter_instance, vm_id, name], mem)
        vm_count.add_metric([self.vcenter_instance], len(vms))
        yield vm_info
        yield vm_cpu
        yield vm_memory_mib
        yield vm_count

    def _collect_performance(self):
        """Collect host and VM performance from stats API, with PerformanceManager fallback when REST fails or returns no data."""
        logger.debug("Performance collection: starting")
        end_sec = int(time.time())
        start_sec = end_sec - 300  # last 5 minutes
        host_id_to_name: dict[str, str] = {}
        vm_id_to_name: dict[str, str] = {}
        try:
            for h in self.client.list_hosts():
                hid = h.get("host") or ""
                if hid:
                    host_id_to_name[hid] = h.get("name") or hid
            for v in self.client.list_vms():
                vid = v.get("vm") or ""
                if vid:
                    vm_id_to_name[vid] = v.get("name") or vid
            logger.debug("Performance collection: host map len=%d vm map len=%d", len(host_id_to_name), len(vm_id_to_name))
        except Exception as e:
            logger.debug("Could not build resource name maps: %s", e, exc_info=True)

        points: list[tuple[str, str, str, float]] = []
        try:
            available = self.client.get_vstats_metrics()
        except VCenterAPIError as e:
            _log_perf_failure("metrics", e)
        else:
            if not available:
                logger.debug("vStats metrics: empty list")
            else:
                metrics_to_use = list(dict.fromkeys(m for m in (VSTATS_METRICS_HOST + VSTATS_METRICS_VM) if m in available))
                if not metrics_to_use:
                    metrics_to_use = available[:10]
                    logger.debug("vStats: preferred metrics not in available list, using first 10: %s", metrics_to_use)
                else:
                    logger.debug("vStats: using metrics %s", metrics_to_use)
                rsrcs = [f"type.HOST={hid}" for hid in host_id_to_name] + [f"type.VM={vid}" for vid in vm_id_to_name]
                data: Any = None
                try:
                    data = self.client.get_vstats_data(
                        types=["HOST", "VM"],
                        start_sec=start_sec,
                        end_sec=end_sec,
                        metrics=metrics_to_use,
                        rsrcs=rsrcs,
                    )
                    points = self._parse_vstats_data(data)
                    logger.debug("vStats data parsed: %d points", len(points))
                except VCenterAPIError as e:
                    _log_perf_failure("data", e)
                if not points and data is not None:
                    if isinstance(data, list):
                        logger.debug("vStats parse produced no points; raw list len=%d", len(data))
                    else:
                        logger.debug("vStats parse produced no points; raw data type=%s", type(data).__name__)

        if not points and (host_id_to_name or vm_id_to_name):
            try:
                fallback = perf_manager.query_performance(
                    server=self.client.server,
                    user=self.client.user,
                    password=self.client.password,
                    verify_ssl=self.client.verify_ssl,
                    host_ids=list(host_id_to_name.keys()),
                    vm_ids=list(vm_id_to_name.keys()),
                    host_id_to_name=host_id_to_name,
                    vm_id_to_name=vm_id_to_name,
                )
                if fallback:
                    points = fallback
                    logger.debug("Performance from PerformanceManager fallback: %d points", len(points))
            except Exception as e:
                logger.debug("PerformanceManager fallback failed: %s", e, exc_info=True)

        if not points:
            return

        gauge = GaugeMetricFamily(
            "vcenter_perf_value",
            "vCenter performance metric (stats API or PerformanceManager fallback; latest value)",
            labels=["vcenter", "resource_type", "resource_id", "resource_name", "metric"],
        )
        for (rtype, rid, metric_name, value) in points:
            name = host_id_to_name.get(rid) or vm_id_to_name.get(rid) or rid
            safe_metric = metric_name.replace(".", "_").replace("-", "_")
            gauge.add_metric(
                [self.vcenter_instance, rtype, rid, name, safe_metric],
                float(value),
            )
        logger.debug("Performance collection: exposing vcenter_perf_value with %d series", len(points))
        yield gauge

    def _parse_vstats_data(self, data: Any) -> list[tuple[str, str, str, float]]:
        """Parse vStats API response into (resource_type, resource_id, metric, value)."""
        out: list[tuple[str, str, str, float]] = []
        items = data if isinstance(data, list) else data.get("value", data.get("data", []))
        if not isinstance(items, list):
            logger.debug("_parse_vstats_data: items not a list (type=%s)", type(items).__name__)
            return out
        logger.debug("_parse_vstats_data: iterating %d items", len(items))
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                logger.debug("_parse_vstats_data: item[%d] not dict", i)
                continue
            rsrc = item.get("rsrc") or item.get("resource") or item.get("resource_id") or ""
            if isinstance(rsrc, dict):
                rsrc = rsrc.get("id") or rsrc.get("resource") or ""
            metric = item.get("metric") or item.get("metric_name") or ""
            value = None
            if "value" in item and item["value"] is not None:
                value = item["value"]
            elif "data" in item and isinstance(item["data"], list) and item["data"]:
                last = item["data"][-1]
                value = last.get("value", last.get("v")) if isinstance(last, dict) else None
            elif "values" in item and isinstance(item["values"], list) and item["values"]:
                last = item["values"][-1]
                value = last.get("value", last.get("v")) if isinstance(last, dict) else last
            if value is None or metric == "":
                if i < 3:
                    logger.debug("_parse_vstats_data: item[%d] skip (value=%s metric=%s) keys=%s", i, value, metric, list(item.keys()))
                continue
            try:
                vfloat = float(value)
            except (TypeError, ValueError):
                if i < 3:
                    logger.debug("_parse_vstats_data: item[%d] value not float: %s", i, type(value).__name__)
                continue
            if "type.HOST=" in str(rsrc):
                rtype = "HOST"
                rid = str(rsrc).split("=", 1)[-1].strip()
            elif "type.VM=" in str(rsrc):
                rtype = "VM"
                rid = str(rsrc).split("=", 1)[-1].strip()
            else:
                rid = str(rsrc)
                rtype = "UNKNOWN"
            out.append((rtype, rid, metric, vfloat))
        return out
