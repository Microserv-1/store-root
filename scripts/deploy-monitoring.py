import argparse
import subprocess
parser = argparse.ArgumentParser()
parser.add_argument("--context", required=True)
args = parser.parse_args()
base = ["kubectl", "--context", args.context, "-n", "store"]
for name,path in [
    ("grafana-datasources", "infra/monitoring/grafana/provisioning/datasources/prometheus.yaml"),
    ("grafana-provider", "infra/monitoring/grafana/provisioning/dashboards/store.yaml"),
    ("grafana-dashboard", "infra/monitoring/grafana/dashboards/store.json"),
]:
    manifest = subprocess.check_output(base+["create", "configmap", name, "--from-file="+path, "--dry-run=client", "-o", "yaml"])
    subprocess.run(base+["apply", "-f", "-"], input=manifest, check=True)
for path in ["infra/k8s/monitoring.yaml", "infra/k8s/grafana.yaml"]:
    subprocess.run(base+["apply", "-f", path], check=True)
