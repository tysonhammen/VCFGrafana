# vCenter Grafana dashboards

Pre-built Grafana dashboards show **clusters**, **hosts**, **storage**, **VMs**, **performance** (CPU/memory), and **vSAN health**. They use template variables so you can filter by vCenter, cluster, datastore, and power state.

## Prerequisites

- **Prometheus** scraping the vcenter-exporter (see main [README](../README.md)).
- **Grafana** with a Prometheus data source configured.

## Dashboards

| Dashboard        | Description |
|------------------|-------------|
| **vCenter Overview** | Summary: total clusters, hosts, VMs, datastores; exporter health; tables for clusters, hosts by connection state, VMs by power state, total storage free %. Links to all other dashboards. |
| **vCenter Clusters** | Table of all clusters (filter by vCenter). Top links to other dashboards. |
| **vCenter Hosts**     | Table of all hosts with connection state and power state; filter by vCenter and cluster. **Click a host name** to open Host Performance for that host. Connection/power cells are color-coded. |
| **vCenter Host Performance** | CPU and memory time series and gauges for ESXi hosts. **Click a series name (legend) or a host in the table** to view that host only. Top links to other dashboards. |
| **vCenter Storage**  | Datastore free %, capacity, and free space; filter by vCenter and datastore name. |
| **vCenter VMs**      | Table of all VMs with power state, guest OS, cluster, host. **Click a VM name** to open VM Performance for that VM. Filter by vCenter, cluster, and power state. Power cells are color-coded. |
| **vCenter VM Performance** | CPU and memory time series and gauges for VMs. **Click a series name (legend) or a VM in the table** to view that VM only. Top links to other dashboards. |
| **vCenter vSAN Health**    | vSAN cluster health score and per-host status (green/yellow/red). **Click a host name** to open Host Performance for that host. Top links to other dashboards. |

## Import in Grafana

1. In Grafana, go to **Dashboards** → **New** → **Import**.
2. Click **Upload JSON file** and choose one of the JSON files in this folder, or paste the file contents.
3. Select your **Prometheus** data source and click **Import**.

Repeat for each dashboard you want, or use provisioning (below).

## Variables

Each dashboard defines:

- **Data source** – Prometheus (set at import; change in dashboard settings if needed).
- **App** – From `label_values(..., app)`. Use this when your Prometheus scrape config adds an `app` label (e.g. `app: "vCenter"`); choose one or “All”.
- **vCenter** – Dropdown from `label_values(vcenter_*_total, vcenter)`. Choose one or “All”.
- **Cluster** (Hosts, VMs) – Filter by cluster.
- **Datastore** (Storage) – Filter by datastore name.
- **Power state** (VMs) – Filter by POWERED_ON, POWERED_OFF, etc.

All variables support “All” so the view stays dynamic when you have multiple vCenters or clusters.

## Drill-down and dashboard links

- **Top bar:** Every dashboard includes links (Overview, Clusters, Hosts, Host Performance, VMs, VM Performance, Storage, vSAN Health) so you can jump between dashboards without using the menu.
- **Click a host or VM name:** On **vCenter Hosts**, **vCenter VMs**, **vCenter Host Performance**, **vCenter VM Performance**, and **vCenter vSAN Health**, clicking a host or VM name (in tables or in chart legends) opens the performance dashboard filtered to that asset so you see full metrics for that host or VM.

## Performance metrics (vStats)

The **vCenter Host Performance** and **vCenter VM Performance** dashboards use the metric `vcenter_perf_value`, which is populated when the exporter can reach the vSphere **vStats** API (Technology Preview). If your vCenter supports vStats, the exporter will collect CPU and memory usage for hosts and VMs and expose them as gauges; the performance dashboards will then show time series and current values. If vStats is not available or returns no data, those dashboards will be empty and the variable dropdowns may show “No data”—in that case use the inventory dashboards (Hosts, VMs, Overview) which do not depend on vStats.

To load these dashboards automatically when Grafana starts, use dashboard provisioning.

1. Copy the provisioning config and dashboards into Grafana’s provisioning paths (paths depend on how you run Grafana; examples below).

2. **Dashboard provider** – create a YAML file that points at this folder, e.g.:

   **`/etc/grafana/provisioning/dashboards/vcenter.yaml`** (Linux) or **`<grafana_install>/conf/provisioning/dashboards/vcenter.yaml`**:

   ```yaml
   apiVersion: 1
   providers:
     - name: 'vcenter'
       orgId: 1
       folder: 'vCenter'
       type: file
       disableDeletion: false
       updateIntervalSeconds: 30
       options:
         path: /etc/grafana/provisioning/dashboards/vcenter
   ```

3. **Copy dashboard JSON files** into the path you set (e.g. `/etc/grafana/provisioning/dashboards/vcenter/`):

   ```bash
   sudo mkdir -p /etc/grafana/provisioning/dashboards/vcenter
   sudo cp dashboards/*.json /etc/grafana/provisioning/dashboards/vcenter/
   ```

4. Restart Grafana. The dashboards appear under the **vCenter** folder (or the folder name you set).

If you run Grafana in Docker, mount the repo’s `dashboards` folder as the provisioning path:

```yaml
volumes:
  - ./dashboards:/etc/grafana/provisioning/dashboards/vcenter:ro
```

and use that path in the provider’s `path` option.

## Refresh

Dashboards use a **30s** refresh by default. You can change it in the time picker (top right). Because the exporter is scraped on an interval (e.g. 5m), data will only change after each scrape.

## vSAN metrics

The **vCenter vSAN Health** dashboard uses `vcenter_vsan_cluster_health_score` and `vcenter_vsan_host_health_status`, which are populated when the exporter can query the vSAN Cluster Health API (via pyvmomi and optionally vsanapiutils/vsanmgmtObjects from the [vcf-sdk-python samples](https://github.com/vmware/vcf-sdk-python/tree/main/vsphere-samples/pyvmomi-community-samples/samples/vsan)). If vSAN collection is disabled or the API is unavailable, the vSAN dashboard will show no data.
