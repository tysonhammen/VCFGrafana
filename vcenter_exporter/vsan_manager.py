"""
vSAN cluster health metrics via vSphere Web Services API (VsanVcClusterHealthSystem).

Based on the vcf-sdk-python sample:
https://github.com/vmware/vcf-sdk-python/blob/main/vsphere-samples/pyvmomi-community-samples/samples/vsan/vsanapisamples.py

- Connects to vCenter with pyvmomi, builds a vSAN stub for /vsanHealth.
- Queries QueryClusterHealthSummary() for each cluster (fetchFromCache=True).
- Returns cluster health score and per-host status for Prometheus.

Requires pyvmomi. For vSAN types (VsanVcClusterHealthSystem) the vcf-sdk-python
samples include vsanapiutils.py and vsanmgmtObjects.py; if not available we try
a minimal stub and skip vSAN collection with a log message.
"""

import logging
import ssl
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from pyVim.connect import SmartConnect, Disconnect
    import pyVmomi
    from pyVmomi import SoapStubAdapter
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False
    pyVmomi = None  # type: ignore

# Optional: vSAN SDK helpers from vcf-sdk-python samples (vsanapiutils + vsanmgmtObjects)
try:
    import vsanapiutils
    HAS_VSAN_UTILS = True
except ImportError:
    HAS_VSAN_UTILS = False
    vsanapiutils = None  # type: ignore

VSAN_API_VC_ENDPOINT = "/vsanHealth"
VSAN_VMODL_VERSION = "vsan.version.version3"


def _parse_server_host(server: str) -> tuple[str, int]:
    """Extract hostname and port from vCenter URL."""
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


def _get_vsan_stub(si_stub: Any, verify_ssl: bool) -> Any:
    """Build a SoapStubAdapter for the vCenter vSAN /vsanHealth endpoint."""
    if not HAS_PYVMOMI:
        return None
    host_str = getattr(si_stub, "host", "") or ""
    if ":" in host_str:
        idx = host_str.rfind(":")
        hostname = host_str[:idx]
        try:
            port = int(host_str[idx + 1 :])
        except ValueError:
            port = 443
    else:
        hostname = host_str
        port = 443
    context = None
    if not verify_ssl:
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        except Exception:
            pass
    vsan_stub = SoapStubAdapter(
        host=hostname,
        port=port,
        path=VSAN_API_VC_ENDPOINT,
        version=VSAN_VMODL_VERSION,
        sslContext=context,
    )
    vsan_stub.cookie = getattr(si_stub, "cookie", None)
    return vsan_stub


def _get_clusters(content: Any) -> list[Any]:
    """Return all ClusterComputeResource objects (vSAN or not)."""
    if not HAS_PYVMOMI or pyVmomi is None:
        return []
    vim = pyVmomi.vim
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.ClusterComputeResource], True
    )
    try:
        return list(container.view)
    finally:
        try:
            container.Destroy()
        except Exception:
            pass


def query_vsan_health(
    server: str,
    user: str,
    password: str,
    verify_ssl: bool,
) -> list[dict[str, Any]]:
    """
    Query vSAN cluster health for all clusters. Uses vsanapiutils when available,
    otherwise a minimal stub (pyvmomi only). Returns list of:
      {"cluster_id": str, "cluster_name": str, "health_score": float,
       "hosts": [{"hostname": str, "status": str}, ...]}
    """
    if not HAS_PYVMOMI:
        logger.debug("pyvmomi not installed; skipping vSAN health")
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
        logger.debug("vSAN SmartConnect failed: %s", e)
        return []
    if si is None:
        return []
    results: list[dict[str, Any]] = []
    try:
        content = si.RetrieveContent()
        clusters = _get_clusters(content)
        if not clusters:
            logger.debug("vSAN: no clusters found")
            return []

        vhs = None
        if HAS_VSAN_UTILS and vsanapiutils is not None:
            try:
                api_version = getattr(
                    vsanapiutils,
                    "GetLatestVmodlVersion",
                    lambda h, p: VSAN_VMODL_VERSION,
                )(hostname, port)
                vc_mos = vsanapiutils.GetVsanVcMos(
                    si._stub,
                    context=ssl.create_default_context() if verify_ssl else None,
                    version=api_version,
                )
                vhs = vc_mos.get("vsan-cluster-health-system")
            except Exception as e:
                logger.debug("vSAN vsanapiutils GetVsanVcMos failed: %s", e)
        if vhs is None:
            try:
                vsan_stub = _get_vsan_stub(si._stub, verify_ssl)
                if vsan_stub is not None:
                    vhs = vim.cluster.VsanVcClusterHealthSystem(
                        "vsan-cluster-health-system", vsan_stub
                    )
            except Exception as e:
                logger.info(
                    "vSAN health system not available (pyvmomi only). "
                    "For vSAN metrics, add vsanapiutils.py and vsanmgmtObjects.py "
                    "from vcf-sdk-python samples to your path: %s",
                    e,
                )
                return []
        if vhs is None:
            return []

        for cluster in clusters:
            try:
                cluster_name = getattr(cluster, "name", None) or ""
                cluster_id = getattr(cluster, "_moId", "") or ""
                summary = vhs.QueryClusterHealthSummary(
                    cluster=cluster,
                    includeObjUuids=False,
                    fetchFromCache=True,
                )
            except Exception as e:
                logger.debug("vSAN QueryClusterHealthSummary for %s failed: %s", cluster_name or cluster_id, e)
                continue
            health_score: Optional[float] = None
            if hasattr(summary, "healthScore") and summary.healthScore is not None:
                try:
                    health_score = float(summary.healthScore)
                except (TypeError, ValueError):
                    pass
            hosts_list: list[dict[str, str]] = []
            if hasattr(summary, "clusterStatus") and summary.clusterStatus is not None:
                status_obj = summary.clusterStatus
                if hasattr(status_obj, "trackedHostsStatus") and status_obj.trackedHostsStatus:
                    for hs in status_obj.trackedHostsStatus:
                        hname = getattr(hs, "hostname", None) or ""
                        hstatus = getattr(hs, "status", None) or ""
                        if isinstance(hstatus, str):
                            pass
                        else:
                            hstatus = str(getattr(hstatus, "name", hstatus))
                        hosts_list.append({"hostname": str(hname), "status": str(hstatus)})
            results.append({
                "cluster_id": str(cluster_id),
                "cluster_name": str(cluster_name),
                "health_score": health_score if health_score is not None else float("nan"),
                "hosts": hosts_list,
            })
    finally:
        try:
            Disconnect(si)
        except Exception:
            pass
    return results
