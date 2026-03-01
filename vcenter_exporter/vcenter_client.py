"""
vSphere Automation API client.

Uses the vCenter REST API as documented at:
https://developer.broadcom.com/xapis/vsphere-automation-api/latest/

Authentication: POST /api/session with Basic auth, then use
vmware-api-session-id header on subsequent requests.
"""

import logging
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class VCenterAPIError(Exception):
    """Raised when a vCenter API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: str = ""):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(message)


class VCenterClient:
    """
    Client for the vSphere Automation REST API.

    Session-based authentication; session is refreshed when expired.
    """

    def __init__(
        self,
        server: str,
        user: str,
        password: str,
        verify_ssl: bool = True,
        session_timeout_seconds: int = 25 * 60,
    ):
        self.server = server.rstrip("/")
        self.user = user
        self.password = password
        self.verify_ssl = verify_ssl
        self.session_timeout_seconds = session_timeout_seconds

        self._session: Optional[requests.Session] = None
        self._session_created_at: float = 0.0

    def _ensure_session(self) -> requests.Session:
        """Create or refresh API session if needed."""
        now = time.monotonic()
        if self._session is None or (now - self._session_created_at) > self.session_timeout_seconds:
            self._create_session()
        return self._session

    def _create_session(self) -> None:
        """Create a new API session via POST /api/session."""
        url = f"{self.server}/api/session"
        self._session = requests.Session()
        self._session.verify = self.verify_ssl
        self._session.auth = (self.user, self.password)
        resp = self._session.post(url)
        if resp.status_code != 201:
            raise VCenterAPIError(
                f"Failed to create session: {resp.status_code}",
                status_code=resp.status_code,
                response_text=resp.text,
            )
        # Response body is the session ID string (JSON string)
        session_id = resp.json()
        self._session.auth = None
        self._session.headers["vmware-api-session-id"] = session_id
        self._session_created_at = time.monotonic()
        logger.debug("vCenter API session created")

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        """GET request; returns JSON body. Refreshes session on 401."""
        session = self._ensure_session()
        url = f"{self.server}{path}"
        resp = session.get(url, params=params, timeout=60)
        if resp.status_code == 401:
            self._session = None
            self._create_session()
            resp = session.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            raise VCenterAPIError(
                f"GET {path} failed: {resp.status_code}",
                status_code=resp.status_code,
                response_text=resp.text,
            )
        return resp.json()

    def _list_response(self, data: Any) -> list:
        """Normalize list API response: either {value: [...]} or [...]."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "value" in data:
            return data["value"]
        return []

    def list_clusters(self) -> list[dict]:
        """List all clusters. GET /api/vcenter/cluster."""
        data = self._get("/api/vcenter/cluster")
        return self._list_response(data)

    def list_hosts(self) -> list[dict]:
        """List all hosts. GET /api/vcenter/host."""
        data = self._get("/api/vcenter/host")
        return self._list_response(data)

    def list_datastores(self) -> list[dict]:
        """List all datastores. GET /api/vcenter/datastore."""
        data = self._get("/api/vcenter/datastore")
        return self._list_response(data)

    def list_vms(self) -> list[dict]:
        """List all VMs. GET /api/vcenter/vm (up to 1000 per request; use filter for more)."""
        data = self._get("/api/vcenter/vm")
        return self._list_response(data)

    def get_vstats_metrics(self) -> list[str]:
        """List available vStats metric names. GET /api/vstats/stats/metrics (Technology Preview)."""
        path = "/api/vstats/stats/metrics"
        try:
            logger.debug("vStats metrics: GET %s%s", self.server, path)
            data = self._get(path)
        except VCenterAPIError as e:
            logger.debug("vStats metrics %s failed: %s %s", path, e.status_code, e.response_text[:200] if e.response_text else "")
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
            logger.debug("vStats metrics: response type=%s keys=%s", type(data).__name__, list(data.keys()) if isinstance(data, dict) else "n/a")
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
        """Get vStats data points. GET /api/vstats/stats/data/dp (Technology Preview)."""
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
            out = self._get(path, params=params)
            logger.debug("vStats data: response type=%s", type(out).__name__)
            if isinstance(out, dict):
                logger.debug("vStats data: keys=%s", list(out.keys()))
                for k, v in out.items():
                    if isinstance(v, list):
                        logger.debug("vStats data: %s len=%d sample=%s", k, len(v), v[:2] if v else None)
                    else:
                        logger.debug("vStats data: %s=%s", k, repr(v)[:150])
            elif isinstance(out, list):
                logger.debug("vStats data: list len=%d sample=%s", len(out), out[:2] if out else None)
            return out
        except VCenterAPIError as e:
            logger.debug("vStats data %s failed: %s body=%s", path, e.status_code, (e.response_text or "")[:300])
            if e.status_code in (404, 501, 400):
                path_alt = "/api/stats/data/dp"
                logger.debug("vStats data: trying GET %s%s", self.server, path_alt)
                return self._get(path_alt, params=params)
            raise

    def close(self) -> None:
        """Release session (optional; DELETE /api/session)."""
        if self._session is None:
            return
        try:
            self._session.delete(f"{self.server}/api/session", timeout=5)
        except Exception as e:
            logger.debug("Session delete failed: %s", e)
        self._session = None
