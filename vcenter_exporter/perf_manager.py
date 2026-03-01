"""
Performance metrics via vSphere Web Services API (PerformanceManager).

Follows the pattern from vcf-sdk-python samples:

- VM: vm_perf_example.py
  https://github.com/vmware/vcf-sdk-python/blob/main/vsphere-samples/pyvmomi-community-samples/samples/vm_perf_example.py
- Host: esxi_perf_sample.py (same QuerySpec/QueryPerf pattern for HostSystem)
  https://github.com/vmware/vcf-sdk-python/blob/main/vsphere-samples/pyvmomi-community-samples/samples/esxi_perf_sample.py

- Build counter map from perfManager.perfCounter: full_name = groupInfo.key + "." + nameInfo.key + "." + rollupType
- QueryAvailablePerfMetric(entity) for available counter IDs per entity
- QuerySpec(entity, metricId=[MetricId(counterId=cid, instance="*")], maxSample=1) for real-time
- QueryPerf(querySpec=[spec]) and parse result base.value[].id.counterId, .value[0]

This module is used as a fallback when the REST vStats/stats APIs are unavailable.
Requires pyvmomi (optional dependency).
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Try optional pyvmomi; do not fail if missing
try:
    from pyVim.connect import SmartConnect, Disconnect
    import pyVmomi
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False
    pyVmomi = None  # type: ignore


# Counter name patterns we want (group.name.rollupType); match perfCounter keys (e.g. cpu.usagemhz.LATEST, cpu.usage.average).
PERF_COUNTER_PATTERNS = [
    "cpu.usagemhz.average",
    "cpu.usage.average",
    "mem.usage.average",
    "cpu.usagemhz.latest",
    "cpu.usage.latest",
    "mem.usage.latest",
]


def _parse_server_host(server: str) -> tuple[str, int]:
    """Extract hostname and port from vCenter URL for pyvmomi."""
    server = (server or "").strip().rstrip("/")
    if server.startswith("https://"):
        server = server[8:]
        default_port = 443
    elif server.startswith("http://"):
        server = server[7:]
        default_port = 80
    else:
        default_port = 443
    if "/" in server:
        server = server.split("/")[0]
    if ":" in server:
        host, port_str = server.rsplit(":", 1)
        try:
            return host, int(port_str)
        except ValueError:
            return host, default_port
    return server, default_port


def _build_counter_map(perf_manager: Any) -> dict[str, int]:
    """Build full_name -> counterId from perfManager.perfCounter (same as vm_perf_example.py)."""
    counter_info: dict[str, int] = {}
    for counter in getattr(perf_manager, "perfCounter", []) or []:
        try:
            group = getattr(counter.groupInfo, "key", "") or ""
            name = getattr(counter.nameInfo, "key", "") or ""
            rollup = getattr(counter, "rollupType", None)
            rollup_str = getattr(rollup, "key", str(rollup)) if rollup else ""
            full_name = f"{group}.{name}.{rollup_str}"
            counter_info[full_name] = counter.key
        except Exception as e:
            logger.debug("Skip counter %s: %s", counter, e)
    return counter_info


def _metric_ids_for_entity(perf_manager: Any, counter_map: dict[str, int], entity: Any) -> list[Any]:
    """Build MetricId list for entity (QueryAvailablePerfMetric then filter to wanted counter IDs)."""
    if not HAS_PYVMOMI or pyVmomi is None:
        return []
    vim = pyVmomi.vim
    available = perf_manager.QueryAvailablePerfMetric(entity=entity)
    if not available:
        return []
    patterns_lower = [p.lower() for p in PERF_COUNTER_PATTERNS]
    wanted = set()
    for full_name, cid in counter_map.items():
        if full_name.lower() in patterns_lower or any(p in full_name.lower() for p in ("cpu.usage", "mem.usage")):
            wanted.add(cid)
    metric_ids = []
    for m in available:
        cid = m.counterId
        if cid in wanted or not wanted:
            metric_ids.append(vim.PerformanceManager.MetricId(counterId=cid, instance="*"))
            if wanted and len(metric_ids) >= 20:
                break
    if not metric_ids and available:
        for m in available[:10]:
            metric_ids.append(vim.PerformanceManager.MetricId(counterId=m.counterId, instance="*"))
    return metric_ids


def query_performance(
    server: str,
    user: str,
    password: str,
    verify_ssl: bool,
    host_ids: list[str],
    vm_ids: list[str],
    host_id_to_name: dict[str, str],
    vm_id_to_name: dict[str, str],
    time_window_seconds: int = 300,
) -> list[tuple[str, str, str, float]]:
    """
    Query PerformanceManager for host and VM metrics (real-time, maxSample=1).

    Follows vm_perf_example.py: QuerySpec(entity, metricId, maxSample=1), QueryPerf.
    Returns list of (resource_type, resource_id, metric_name, value).
    """
    if not HAS_PYVMOMI:
        logger.debug("pyvmomi not installed; skipping PerformanceManager path")
        return []
    vim = pyVmomi.vim
    hostname, port = _parse_server_host(server)
    si = None
    try:
        si = SmartConnect(
            host=hostname,
            user=user,
            pwd=password,
            port=port,
            disableSslCertValidation=not verify_ssl,
        )
    except Exception as e:
        logger.info("PerformanceManager SmartConnect failed: %s", e)
        return []
    if si is None:
        return []
    try:
        content = si.RetrieveContent()
        perf_manager = content.perfManager
        if not perf_manager:
            logger.info("PerformanceManager: vCenter has no perfManager (performance not available)")
            return []
        counter_map = _build_counter_map(perf_manager)
        id_to_name: dict[int, str] = {v: k for k, v in counter_map.items()}
        if not counter_map:
            logger.info("PerformanceManager: no perfCounter list from vCenter (performance counters may be disabled)")
            return []

        results: list[tuple[str, str, str, float]] = []
        entities_specs: list[tuple[str, str, Any]] = []
        first_mor_error: Optional[str] = None

        def _make_mor(mo_type: str, mo_id: str) -> Any:
            """Build ManagedObjectReference; try constructor then attr-based."""
            try:
                return vim.ManagedObjectReference(mo_type, mo_id)
            except Exception as e1:
                pass
            try:
                return vim.ManagedObjectReference(type=mo_type, value=mo_id)
            except Exception as e2:
                pass
            try:
                mo = vim.ManagedObjectReference()
                setattr(mo, "type", mo_type)
                mo.value = mo_id
                return mo
            except Exception as e3:
                pass
            try:
                mo = vim.ManagedObjectReference()
                mo._type = mo_type
                mo.value = mo_id
                return mo
            except Exception as e4:
                raise type(e1)(f"{mo_type} {mo_id}: {e1!s}; {e4!s}") from e4

        for hid in host_ids:
            try:
                mo = _make_mor("HostSystem", hid)
                entities_specs.append(("HOST", hid, mo))
            except Exception as e:
                if first_mor_error is None:
                    first_mor_error = f"HOST {hid}: {e}"
                logger.debug("PerformanceManager: could not build MOR for HOST %s: %s", hid, e)
        for vid in vm_ids:
            try:
                mo = _make_mor("VirtualMachine", vid)
                entities_specs.append(("VM", vid, mo))
            except Exception as e:
                if first_mor_error is None:
                    first_mor_error = f"VM {vid}: {e}"
                logger.debug("PerformanceManager: could not build MOR for VM %s: %s", vid, e)
        if not entities_specs and (host_ids or vm_ids):
            logger.info(
                "PerformanceManager: could not build any host/VM managed object refs from IDs%s",
                f" ({first_mor_error})" if first_mor_error else "",
            )
        else:
            n_host = sum(1 for t in entities_specs if t[0] == "HOST")
            n_vm = sum(1 for t in entities_specs if t[0] == "VM")
            logger.debug("PerformanceManager: built %d host, %d VM refs", n_host, n_vm)
        for rtype, rid, entity in entities_specs:
            metric_ids = _metric_ids_for_entity(perf_manager, counter_map, entity)
            if not metric_ids:
                logger.debug("PerformanceManager: no metric IDs for %s %s (QueryAvailablePerfMetric empty or no match)", rtype, rid)
                continue
            try:
                # Real-time: maxSample=1 like vm_perf_example.py (no startTime/endTime)
                spec = vim.PerformanceManager.QuerySpec(
                    entity=entity,
                    metricId=metric_ids,
                    maxSample=1,
                )
                query_result = perf_manager.QueryPerf(querySpec=[spec])
            except Exception as e:
                logger.info("PerformanceManager QueryPerf failed for %s %s: %s", rtype, rid, e)
                continue
            if not query_result:
                logger.debug("PerformanceManager: QueryPerf returned empty for %s %s", rtype, rid)
                continue
            for base in query_result:
                if not getattr(base, "value", None):
                    continue
                for series in base.value:
                    cid = series.id.counterId
                    instance = getattr(series.id, "instance", "") or ""
                    metric_label = id_to_name.get(cid, f"counter_{cid}")
                    metric_safe = metric_label.replace(".", "_").replace("-", "_").lower()
                    if instance and instance != "*":
                        metric_safe = f"{metric_safe}_{instance}"
                    vals = getattr(series, "value", None) or []
                    if vals:
                        try:
                            # Use first sample like vm_perf_example.py: val.value[0]
                            results.append((rtype, rid, metric_safe, float(vals[0])))
                        except (TypeError, ValueError):
                            pass
        if not results and entities_specs:
            logger.info(
                "PerformanceManager: connected but no metrics returned (QueryPerf returned no data for %d host/VMs)",
                len(entities_specs),
            )
    finally:
        try:
            Disconnect(si)
        except Exception:
            pass

    return results
