# vCenter Grafana dashboards

Pre-built Grafana dashboards that show **clusters**, **hosts**, **storage**, and **VMs** from the vCenter Prometheus exporter. They use template variables so you can filter by vCenter, cluster, datastore, and power state.

## Prerequisites

- **Prometheus** scraping the vcenter-exporter (see main [README](../README.md)).
- **Grafana** with a Prometheus data source configured.

## Dashboards

| Dashboard        | Description |
|------------------|-------------|
| **vCenter Overview** | Summary: total clusters, hosts, VMs, datastores; exporter health; tables for clusters, hosts by connection state, VMs by power state, total storage free %. |
| **vCenter Clusters** | Table of all clusters (filter by vCenter). |
| **vCenter Hosts**     | Table of all hosts with connection state and power state; filter by vCenter and cluster. Connection/power cells are color-coded. |
| **vCenter Storage**  | Datastore free %, capacity, and free space; filter by vCenter and datastore name. |
| **vCenter VMs**      | Table of all VMs with power state, guest OS, cluster, host; filter by vCenter, cluster, and power state. Power cells are color-coded. |

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

## Auto-load with provisioning

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
