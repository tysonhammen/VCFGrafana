"""
vCenter client using the VCF SDK for Python (vmware-vcenter).

Requires vmware-vcenter. Uses create_vsphere_client for inventory;
performance metrics (vStats/stats) use the same session.

See: https://github.com/vmware/vcf-sdk-python
"""

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

try:
    from vmware.vapi.vsphere.client import create_vsphere_client
    HAS_VSPHERE_CLIENT = True
except ImportError:
    HAS_VSPHERE_CLIENT = False
    create_vsphere_client = None  # type: ignore


class VCenterAPIError(Exception):
    """Raised when a vCenter API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: str = ""):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(message)


def _summary_to_dict(obj: Any, *keys: str) -> dict:
    """Convert SDK Summary/Info object to dict; use keys for attribute names (snake_case)."""
    out: dict[str, Any] = {}
    for k in keys:
        v = getattr(obj, k, None)
        if v is None:
            out[k] = None
            continue
        if hasattr(v, "string"):
            out[k] = v.string
        elif hasattr(v, "value"):
            out[k] = v.value
        else:
            out[k] = v
    return out


class VCenterClient:
    """
    Client for vCenter using the VCF SDK (vmware-vcenter).

    Requires vmware-vcenter. Uses create_vsphere_client for inventory;
    uses the same HTTP session for stats API calls when needed.
    """

    def __init__(
        self,
        server: str,
        user: str,
        password: str,
        verify_ssl: bool = True,
        session_timeout_seconds: int = 25 * 60,
    ):
        if not HAS_VSPHERE_CLIENT:
            raise VCenterAPIError(
                "vmware-vcenter is not installed. Run the installer with upgrade: ./install.sh --upgrade"
            )
        self.server = server.rstrip("/")
        self.user = user
        self.password = password
        self.verify_ssl = verify_ssl
        self.session_timeout_seconds = session_timeout_seconds

        self._client: Any = None
        self._session: Optional[requests.Session] = None
        self._connect()

    def _connect(self) -> None:
        """Create vSphere client and session."""
        import urllib3
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session = requests.Session()
        session.verify = self.verify_ssl
        session.headers["Content-Type"] = "application/json"
        host = self.server
        if host.startswith("https://"):
            host = host[8:]
        if host.startswith("http://"):
            host = host[7:]
        if "/" in host:
            host = host.split("/")[0]
        self._client = create_vsphere_client(
            server=host,
            username=self.user,
            password=self.password,
            session=session,
        )
        self._session = session
        logger.debug("vCenter SDK client connected")

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        """GET request using the SDK session (for stats API). Returns JSON."""
        if self._session is None:
            self._connect()
        url = f"{self.server}{path}"
        resp = self._session.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            raise VCenterAPIError(
                f"GET {path} failed: {resp.status_code}",
                status_code=resp.status_code,
                response_text=resp.text,
            )
        return resp.json()

    def _list_response(self, data: Any) -> list:
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "value" in data:
            return data["value"]
        return []

    def list_clusters(self) -> list[dict]:
        clusters = self._client.vcenter.Cluster.list()
        out = []
        for c in clusters:
            d = _summary_to_dict(c, "cluster", "name")
            d.setdefault("name", d.get("cluster", "unknown"))
            out.append(d)
        return out

    def list_hosts(self) -> list[dict]:
        hosts = self._client.vcenter.Host.list()
        out = []
        for h in hosts:
            d = _summary_to_dict(h, "host", "name", "connection_state", "power_state", "cluster")
            d.setdefault("connection_state", "UNKNOWN")
            d.setdefault("power_state", "UNKNOWN")
            d.setdefault("cluster", "")
            out.append(d)
        return out

    def list_datastores(self) -> list[dict]:
        datastores = self._client.vcenter.Datastore.list()
        out = []
        for d in datastores:
            row = _summary_to_dict(d, "datastore", "name", "type", "capacity", "free_space")
            row.setdefault("capacity", 0)
            if row.get("free_space") is None:
                row["free_space"] = getattr(d, "free_space", None) or 0
            row.setdefault("freeSpace", row.get("free_space"))
            out.append(row)
        return out

    def list_vms(self) -> list[dict]:
        vms = self._client.vcenter.VM.list()
        out = []
        for v in vms:
            d = _summary_to_dict(
                v, "vm", "name", "power_state", "cpu_count", "memory_size_mib",
                "guest_OS", "cluster", "host",
            )
            d.setdefault("guest_OS", "")
            d.setdefault("cluster", "")
            d.setdefault("host", "")
            placement = getattr(v, "placement", None)
            if placement:
                d["cluster"] = d.get("cluster") or getattr(placement, "cluster", "") or ""
                d["host"] = d.get("host") or getattr(placement, "host", "") or ""
            if d.get("memory_size_mib") is not None:
                d["memory_size_MiB"] = d["memory_size_mib"]
            out.append(d)
        return out

    def get_vstats_metrics(self) -> list[str]:
        path = "/api/vstats/stats/metrics"
        try:
            logger.debug("vStats metrics: GET %s%s", self.server, path)
            data = self._get(path)
        except VCenterAPIError as e:
            if e.status_code in (404, 501, 400):
                path_alt = "/api/stats/metrics"
                try:
                    logger.debug("vStats metrics: trying GET %s%s", self.server, path_alt)
                    data = self._get(path_alt)
                except VCenterAPIError as e2:
                    logger.debug("vStats metrics %s failed: %s", path_alt, e2.status_code)
                    raise e
            else:
                raise
        out = self._list_response(data)
        if not out:
            return []
        result = [m.get("metric", m) if isinstance(m, dict) else str(m) for m in out]
        logger.debug("vStats metrics: got %d metrics, sample: %s", len(result), result[:15])
        return result

    def get_vstats_data(
        self,
        types: list[str],
        start_sec: int,
        end_sec: int,
        metrics: Optional[list[str]] = None,
        rsrcs: Optional[list[str]] = None,
    ) -> Any:
        params: dict[str, Any] = {"start": start_sec, "end": end_sec}
        if types:
            params["types"] = types
        if metrics:
            params["metric"] = list(dict.fromkeys(metrics))
        if rsrcs:
            params["rsrcs"] = rsrcs
        path = "/api/vstats/stats/data/dp"
        try:
            logger.debug("vStats data: GET %s%s params=%s", self.server, path, params)
            return self._get(path, params=params)
        except VCenterAPIError as e:
            if e.status_code in (404, 501, 400):
                path_alt = "/api/stats/data/dp"
                metrics_list = list(dict.fromkeys(metrics)) if metrics else []
                if not metrics_list:
                    logger.debug("vStats data: trying GET %s%s", self.server, path_alt)
                    return self._get(path_alt, params=params)
                logger.debug("vStats data: trying GET %s%s (one metric per request)", self.server, path_alt)
                merged: list[Any] = []
                for one_metric in metrics_list:
                    single_params = {**params, "metric": one_metric}
                    try:
                        out = self._get(path_alt, params=single_params)
                    except VCenterAPIError as e2:
                        logger.debug("vStats data metric=%s failed: %s", one_metric, e2.status_code)
                        continue
                    part = out if isinstance(out, list) else (out.get("value") or out.get("data") or [])
                    if isinstance(part, list):
                        merged.extend(part)
                    else:
                        merged.append(part)
                return merged
            raise

    def close(self) -> None:
        if self._session is None:
            return
        try:
            self._session.delete(f"{self.server}/api/session", timeout=5)
        except Exception as e:
            logger.debug("Session delete failed: %s", e)
        self._session = None
        self._client = None
