"""
Prometheus collector that fetches vCenter inventory and exposes metrics.

Exposes:
- vcenter_cluster_* (clusters)
- vcenter_host_* (hosts)
- vcenter_datastore_* (storage)
- vcenter_vm_* (VMs)
"""

import logging
from typing import Optional

from prometheus_client.core import GaugeMetricFamily, REGISTRY

from .vcenter_client import VCenterClient, VCenterAPIError

logger = logging.getLogger(__name__)


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
