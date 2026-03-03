# vCenter Prometheus Exporter

A **Python** monitoring service that uses the **[VCF SDK for Python](https://github.com/vmware/vcf-sdk-python)** (vmware-vcenter) to expose **vCenter** inventory and basic metrics to **Prometheus**. It monitors:

- **Clusters**
- **Hosts** (ESXi)
- **Storage** (datastores)
- **VMs** (virtual machines)

## Requirements

- Python 3.10+
- vCenter 6.5+ with network access from the exporter (HTTPS, typically 443)
- **[vmware-vcenter](https://github.com/vmware/vcf-sdk-python)** (VCF SDK for Python) for vCenter inventory, authentication, and optional performance metrics via the stats API

## Install with script (Linux)

The install script **must be run as root**. It copies the repository into a system directory (default `/opt/vcenter-exporter`), creates a virtual environment there, and installs a systemd service that runs as root.

1. **Clone or unpack** the repo:
   ```bash
   git clone https://github.com/tysonhammen/VCFGrafana.git
   cd VCFGrafana
   ```

2. **Run the installer as root** (installs to `/opt/vcenter-exporter` by default):
   ```bash
   chmod +x install.sh
   sudo ./install.sh
   ```
   You will be prompted for:
   - **vCenter URL** (e.g. `https://vcenter.example.com`) – required
   - **vCenter user** (default: `administrator@vsphere.local`)
   - **vCenter password** – required (input is hidden)
   - **Verify vCenter SSL certificate?** – Y/n (default Y)
   - **Exporter listen address** (default: `0.0.0.0`)
   - **Exporter port** (default: `9680`)

   The script copies files to `/opt/vcenter-exporter`, creates a `.venv` there, writes `.env`, and installs/enables the systemd service.

3. **Optional:** Install to a different directory:
   ```bash
   sudo ./install.sh --prefix /opt/my-vcenter-exporter
   ```

   **Useful commands:**
   - `systemctl status vcenter-exporter` – status
   - `journalctl -u vcenter-exporter -f` – follow logs
   - `systemctl restart vcenter-exporter` – restart after config/code changes
   - `systemctl stop vcenter-exporter` – stop

## Quick start (manual / development)

If you prefer not to use the install script, you can run the exporter from a clone with a virtual environment:

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

### 2. Configure

Copy the example env file and set your vCenter details:

```bash
cp .env.example .env
```

Edit `.env`:

```env
VCENTER_SERVER=https://vcenter.example.com
VCENTER_USER=administrator@vsphere.local
VCENTER_PASSWORD=your_password
VCENTER_VERIFY_SSL=true
EXPORTER_HOST=0.0.0.0
EXPORTER_PORT=9680
# Optional: log to file and set level (DEBUG for performance/stats API troubleshooting)
# LOG_FILE=/var/log/vcenter-exporter.log
# LOG_LEVEL=DEBUG
#
# Performance collection (can cause long scrapes / Prometheus timeout):
# VCENTER_COLLECT_PERF=true     # set to false or 0 to disable host/VM perf (inventory only)
# VCENTER_PERF_TIMEOUT_SEC=0    # stop perf collection after N seconds (0 = no limit)
# VCENTER_PERF_MAX_HOSTS=0      # cap hosts queried for perf (0 = no limit)
# VCENTER_PERF_MAX_VMS=0        # cap VMs queried for perf (0 = no limit)
# VCENTER_PERF_ASYNC=true      # collect perf in background, serve from cache (avoids scrape timeout)
# VCENTER_PERF_INTERVAL_SEC=300 # when async, refresh cache every N seconds
#
# vSAN health (cluster score + host status; requires pyvmomi):
# VCENTER_COLLECT_VSAN=true
# VCENTER_VSAN_ASYNC=true
# VCENTER_VSAN_INTERVAL_SEC=300
```

- **VCENTER_SERVER** – vCenter URL (with `https://`).
- **VCENTER_USER** / **VCENTER_PASSWORD** – Credentials that can read inventory (clusters, hosts, datastores, VMs).
- **VCENTER_VERIFY_SSL** – Set to `false` only if you use a self-signed certificate and accept the security risk.
- **EXPORTER_HOST** / **EXPORTER_PORT** – Bind address and port for the metrics HTTP server (default `0.0.0.0:9680`).

**Log file and debug logging**

- **LOG_FILE** – Optional. If set, all logs are also written to this file (e.g. `/var/log/vcenter-exporter.log`). Useful when running as a service so you can inspect logs without `journalctl`.
- **LOG_LEVEL** – Optional. Set to `DEBUG` to troubleshoot performance/stats (e.g. why `vcenter_perf_value` is missing). Default `INFO`. Use with `LOG_FILE` to capture debug output to a file.

If the service runs as a non-root user (e.g. when running manually) and you use `LOG_FILE=/var/log/vcenter-exporter.log`, create the file and give that user write permission before starting:

```bash
sudo touch /var/log/vcenter-exporter.log
sudo chown idadm:idadm /var/log/vcenter-exporter.log
```

Alternatively, use a path the user can write without root (e.g. `LOG_FILE=/tmp/vcenter-exporter.log`); the exporter will create parent directories if needed. To change vCenter settings after install, see [Updating from previous versions](#updating-from-previous-versions) (use `--reconfigure`).

### 3. Run the exporter

```bash
python -m vcenter_exporter.main
# or, if installed:
vcenter-exporter
```

Metrics are served at:

```text
http://<host>:9680/metrics
```

### 4. Configure Prometheus

Add a scrape config to `prometheus.yml` (see also `prometheus-vcenter.example.yaml`):

```yaml
scrape_configs:
  - job_name: 'vcenter'
    static_configs:
      - targets: ['srv-vcexp-01.lab.influencedigital.com:9680']
        labels:
          app: "vCenter"
    metrics_path: /metrics
    scrape_interval: 5m
```

Replace the target host/port if needed. The `app` label is used by the Grafana dashboards to filter metrics.

**If scrapes time out** (no data, or Prometheus logs "context deadline exceeded"), performance collection may be taking too long. Either increase the scrape timeout for this job or reduce/disable performance collection (see [Performance collection and scrape timeouts](#performance-collection-and-scrape-timeouts) below).

Reload or restart Prometheus so it scrapes the new target.

### Performance collection and scrape timeouts

Host/VM performance (vStats or PerformanceManager fallback) can take a long time when there are many hosts and VMs, which may cause Prometheus to time out the scrape (default is often 10s). Options:

| Option | Description |
|--------|-------------|
| **Increase scrape timeout** | In `prometheus.yml`, set `scrape_timeout: 60s` (or higher) for the vcenter job so the exporter has time to finish. |
| **Disable performance** | Set `VCENTER_COLLECT_PERF=false` (or `0`) in the exporter's environment. The exporter will return only inventory metrics (clusters, hosts, datastores, VMs) and the scrape stays fast. Host/VM performance dashboards will have no data. |
| **Timeout perf and keep inventory** | Set `VCENTER_PERF_TIMEOUT_SEC=30` (or another value). Performance collection runs in a background thread; if it does not finish within that many seconds, it is abandoned and the scrape returns with inventory only. Avoids a full scrape timeout while still attempting perf. |
| **Limit scope** | Set `VCENTER_PERF_MAX_HOSTS=50` and/or `VCENTER_PERF_MAX_VMS=200` to cap how many entities are queried for performance. Reduces work and scrape time. |
| **Thread perf separately** | Set `VCENTER_PERF_ASYNC=true`. Performance is collected in a **background thread** on an interval (e.g. every 5 minutes). Each scrape returns **inventory immediately** and **cached performance** from the last run. Scrapes stay fast and never wait on perf. Set `VCENTER_PERF_INTERVAL_SEC=300` (default) to match your scrape interval. |

Example: disable performance so scrapes always succeed, then increase timeout later if you want perf:

```env
VCENTER_COLLECT_PERF=false
```

Example: run performance in a background thread so scrapes never wait (recommended if you had timeouts):

```env
VCENTER_PERF_ASYNC=true
VCENTER_PERF_INTERVAL_SEC=300
```

Example Prometheus config with a longer timeout:

```yaml
  - job_name: 'vcenter'
    scrape_interval: 5m
    scrape_timeout: 60s
    static_configs:
      - targets: ['srv-vcexp-01:9680']
        labels:
          app: "vCenter"
    metrics_path: /metrics
```

### vSAN health

When **vSAN** is enabled (`VCENTER_COLLECT_VSAN=true`, default), the exporter queries the vSAN Cluster Health API (QueryClusterHealthSummary) and exposes cluster health score and per-host status. Collection runs in a **background thread** when `VCENTER_VSAN_ASYNC=true` (default), so scrapes stay fast. Requires **pyvmomi**; for best compatibility with all vCenter versions, add **vsanapiutils.py** and **vsanmgmtObjects.py** from the [vcf-sdk-python vsan samples](https://github.com/vmware/vcf-sdk-python/tree/main/vsphere-samples/pyvmomi-community-samples/samples/vsan) to your Python path. The **vCenter vSAN Health** Grafana dashboard visualizes these metrics.

## Exposed metrics

| Metric | Type | Description |
|--------|------|-------------|
| `vcenter_cluster_info` | Gauge | 1 per cluster (labels: `vcenter`, `name`) |
| `vcenter_cluster_total` | Gauge | Total number of clusters |
| `vcenter_host_info` | Gauge | 1 per host (labels: `vcenter`, `host_id`, `name`, `connection_state`, `power_state`, `cluster`) |
| `vcenter_host_total` | Gauge | Total number of hosts |
| `vcenter_datastore_info` | Gauge | 1 per datastore (labels: `vcenter`, `datastore_id`, `name`, `type`) |
| `vcenter_datastore_capacity_bytes` | Gauge | Datastore capacity (bytes) |
| `vcenter_datastore_free_bytes` | Gauge | Datastore free space (bytes) |
| `vcenter_datastore_total` | Gauge | Total number of datastores |
| `vcenter_vm_info` | Gauge | 1 per VM (labels: `vcenter`, `vm_id`, `name`, `power_state`, `guest_os`, `cluster`, `host`) |
| `vcenter_vm_cpu_count` | Gauge | Configured vCPU count per VM |
| `vcenter_vm_memory_mib` | Gauge | Configured memory (MiB) per VM |
| `vcenter_vm_total` | Gauge | Total number of VMs |
| `vcenter_perf_value` | Gauge | Host/VM performance (stats API; labels: `vcenter`, `resource_type`, `resource_id`, `resource_name`, `metric`). Only present when the vCenter stats API is available. |
| `vcenter_vsan_cluster_health_score` | Gauge | vSAN cluster health score 0–100 (labels: `vcenter`, `cluster_id`, `cluster_name`). Only when vSAN collection enabled. |
| `vcenter_vsan_host_health_status` | Gauge | vSAN host health: 1=green, 0.5=yellow, 0=red/gray (labels: `vcenter`, `cluster_id`, `cluster_name`, `host`, `status`). Only when vSAN collection enabled. |
| `vcenter_scrape_error` | Gauge | 1 if last scrape failed, 0 on success (for alerting) |

## API reference

The exporter uses the **[VCF SDK for Python](https://github.com/vmware/vcf-sdk-python)** (vmware-vcenter) to connect to vCenter:

- **Connection:** `create_vsphere_client(server, username, password, session)` from `vmware.vapi.vsphere.client`
- **Inventory:** `vcenter.Cluster.list()`, `vcenter.Host.list()`, `vcenter.Datastore.list()`, `vcenter.VM.list()`
- **Performance (optional):** When the vCenter stats API is available, the exporter uses a REST session to call `/api/stats/metrics` and `/api/stats/data/dp` for CPU/memory metrics (with explicit host/VM resources).

See [VCF SDK for Python](https://github.com/vmware/vcf-sdk-python) for documentation.

## Grafana

Pre-built dashboards are in the **[dashboards/](dashboards/)** folder. Import the JSON files via **Dashboards** → **Import** → **Upload JSON file**, or use [Grafana provisioning](dashboards/README.md#auto-load-with-provisioning) to load them automatically.

Use Prometheus as a data source and build dashboards from the `vcenter_*` metrics. Example queries:

- Clusters: `count(vcenter_cluster_info) by (vcenter, name)`
- Hosts by connection state: `count(vcenter_host_info) by (connection_state)`
- Datastore usage: `vcenter_datastore_free_bytes / vcenter_datastore_capacity_bytes`
- VMs by power state: `count(vcenter_vm_info) by (power_state)`

## Updating from previous versions

After pulling new code in your clone, upgrade the installed copy in `/opt/vcenter-exporter` and restart the service:

1. **Pull the latest code** (in your clone):
   ```bash
   cd /path/to/VCFGrafana
   git pull origin main
   ```

2. **Run the upgrade** (copies files and refreshes the venv at the install prefix):
   ```bash
   sudo ./install.sh --upgrade
   ```
   This copies the updated repo to `/opt/vcenter-exporter`, runs `pip install --upgrade -r requirements.txt` and `pip install -e .` there, and restarts the service. Use `sudo ./install.sh --prefix /path/to/install --upgrade` if you installed to a different directory.

3. **Reconfigure** (change vCenter URL, password, etc.) without reinstalling:
   ```bash
   sudo ./install.sh --reconfigure
   ```
   Use `--prefix /path` if you installed to a non-default path.

## License

MIT
