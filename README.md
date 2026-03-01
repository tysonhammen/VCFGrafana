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

Reload or restart Prometheus so it scrapes the new target.

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
