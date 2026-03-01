# vCenter Prometheus Exporter

A **Python** monitoring service that uses the [vSphere Automation API](https://developer.broadcom.com/xapis/vsphere-automation-api/latest/) to expose **vCenter** inventory and basic metrics to **Prometheus**. It monitors:

- **Clusters**
- **Hosts** (ESXi)
- **Storage** (datastores)
- **VMs** (virtual machines)

## Requirements

- Python 3.10+
- vCenter 6.5+ with vSphere Automation API (REST) enabled
- Network access from the exporter to vCenter (HTTPS, typically 443)

## Install with script (Linux)

On Linux you can use the install script to gather configuration interactively, create a virtual environment, and optionally install and enable a systemd service.

1. **Clone or unpack** the repo and go to its directory:
   ```bash
   cd /path/to/VCFGrafana
   ```

2. **Run the installer** (as the user that will own the process, not root):
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
   You will be prompted for:
   - **vCenter URL** (e.g. `https://vcenter.example.com`) – required
   - **vCenter user** (default: `administrator@vsphere.local`)
   - **vCenter password** – required (input is hidden)
   - **Verify vCenter SSL certificate?** – Y/n (default Y)
   - **Exporter listen address** (default: `0.0.0.0`)
   - **Exporter port** (default: `9680`)

   The script creates `.env`, a `.venv` virtual environment, and installs the package.

3. **Install and enable the systemd service** (so the exporter runs on boot and restarts on failure):
   ```bash
   sudo ./install.sh --install-systemd
   ```
   This creates `/etc/systemd/system/vcenter-exporter.service`, enables it, and starts it. The service runs as the user that owns the repo directory.

   **Useful commands:**
   - `sudo systemctl status vcenter-exporter` – status
   - `journalctl -u vcenter-exporter -f` – follow logs
   - `sudo systemctl restart vcenter-exporter` – restart after config/code changes
   - `sudo systemctl stop vcenter-exporter` – stop

   To **re-run the installer** (e.g. to change config), run `./install.sh` again. If `.env` already exists, you will be asked whether to overwrite it.

## Quick start

### 1. Install dependencies

**Option A – no root (recommended)**  
Use a virtual environment or install into your user directory:

```bash
# Using a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
# or: pip install -e .

# Or install into your user directory (no venv)
pip install --user -r requirements.txt
# or: pip install --user -e .
```

**Option B – system install (requires root)**

```bash
pip install -r requirements.txt
# or: sudo pip install -e .
```

If you see **Permission denied** writing to `/usr/local/...`, use Option A (venv or `pip install --user`).

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
```

- **VCENTER_SERVER** – vCenter URL (with `https://`).
- **VCENTER_USER** / **VCENTER_PASSWORD** – Credentials that can read inventory (clusters, hosts, datastores, VMs).
- **VCENTER_VERIFY_SSL** – Set to `false` only if you use a self-signed certificate and accept the security risk.
- **EXPORTER_HOST** / **EXPORTER_PORT** – Bind address and port for the metrics HTTP server (default `0.0.0.0:9680`).

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
| `vcenter_scrape_error` | Gauge | 1 if last scrape failed, 0 on success (for alerting) |

## API reference

The exporter uses the vSphere Automation REST API:

- **Authentication:** `POST /api/session` (Basic auth) → session ID in response; subsequent requests use header `vmware-api-session-id`.
- **Clusters:** `GET /api/vcenter/cluster`
- **Hosts:** `GET /api/vcenter/host`
- **Datastores:** `GET /api/vcenter/datastore`
- **VMs:** `GET /api/vcenter/vm`

See [vSphere Automation API](https://developer.broadcom.com/xapis/vsphere-automation-api/latest/) for full documentation.

## Grafana

Pre-built dashboards are in the **[dashboards/](dashboards/)** folder. Import the JSON files via **Dashboards** → **Import** → **Upload JSON file**, or use [Grafana provisioning](dashboards/README.md#auto-load-with-provisioning) to load them automatically.

Use Prometheus as a data source and build dashboards from the `vcenter_*` metrics. Example queries:

- Clusters: `count(vcenter_cluster_info) by (vcenter, name)`
- Hosts by connection state: `count(vcenter_host_info) by (connection_state)`
- Datastore usage: `vcenter_datastore_free_bytes / vcenter_datastore_capacity_bytes`
- VMs by power state: `count(vcenter_vm_info) by (power_state)`

## Updating from previous versions

To upgrade to the latest release:

1. **Pull the latest code** (if you cloned the repo):
   ```bash
   git pull origin main
   ```

2. **Refresh dependencies**:
   ```bash
   pip install -r requirements.txt --upgrade
   ```
   If you installed the package in editable mode (use `--user` if you don’t have root):
   ```bash
   pip install -e . --upgrade
   ```

3. **Restart the exporter** so it runs the new code:
   ```bash
   # If running under systemd, for example:
   sudo systemctl restart vcenter-exporter
   # Or stop the current process (Ctrl+C) and start again:
   python -m vcenter_exporter.main
   ```

4. **Check the changelog** (if present) for any config or metric changes that might affect your Prometheus scrapes or Grafana dashboards. No config changes are required for the current release.

## License

MIT
