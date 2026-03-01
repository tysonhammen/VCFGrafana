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

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
# or install the package
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

Add a scrape config to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'vcenter'
    static_configs:
      - targets: ['<exporter_host>:9680']
    metrics_path: /metrics
    scrape_interval: 5m
```

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

Use Prometheus as a data source and build dashboards from the `vcenter_*` metrics. Example queries:

- Clusters: `count(vcenter_cluster_info) by (vcenter, name)`
- Hosts by connection state: `count(vcenter_host_info) by (connection_state)`
- Datastore usage: `vcenter_datastore_free_bytes / vcenter_datastore_capacity_bytes`
- VMs by power state: `count(vcenter_vm_info) by (power_state)`

## License

MIT
