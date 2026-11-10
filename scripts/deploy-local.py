"""Cross-platform local Kubernetes deployment script for all 6 services + dependencies."""
import argparse
import subprocess
import sys

ALL_SERVICES = ("account", "auth", "product", "exchange", "order", "gateway")

parser = argparse.ArgumentParser()
parser.add_argument("--context", required=True)
args = parser.parse_args()


def kubectl(*cmd: str):
    subprocess.run(["kubectl", "--context", args.context, *cmd], check=True)


kubectl("apply", "-f", "infra/k8s/namespace.yaml")
subprocess.run([sys.executable, "scripts/k8s-secrets.py", "--context", args.context, "--local-database"], check=True)
kubectl("apply", "-f", "infra/k8s/postgres-local.yaml")
kubectl("apply", "-f", "infra/k8s/dependencies-b.yaml")
for dep in ("postgres", "redis", "rabbitmq"):
    kubectl("rollout", "status", f"deployment/{dep}", "-n", "store", "--timeout=180s")
for service in ALL_SERVICES:
    kubectl("apply", "-f", f"api/{service}/k8s/k8s.yaml")
for service in ALL_SERVICES:
    kubectl("rollout", "status", f"deployment/{service}", "-n", "store", "--timeout=180s")
subprocess.run([sys.executable, "scripts/deploy-monitoring.py", "--context", args.context], check=True)
print("Ready. Forward gateway: kubectl --context", args.context, "-n store port-forward service/gateway 8080:8000")
