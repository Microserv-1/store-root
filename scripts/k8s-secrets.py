"""Send secrets to kubectl via stdin; never emit secrets into logs or files."""
import argparse
import base64
import json
import subprocess
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--context", required=True, help="Explicit Kubernetes context")
parser.add_argument("--env-file", default=".env")
parser.add_argument("--local-database", action="store_true")
args = parser.parse_args()
env = dict(line.split("=", 1) for line in Path(args.env_file).read_text().splitlines() if line and not line.startswith("#"))
keys = ["JWT_SECRET", "INTERNAL_AUTH_KEY", "GRAFANA_PASSWORD"]
if args.local_database:
    keys += ["POSTGRES_PASSWORD"]
    env["DATABASE_URL"] = f"postgresql+psycopg://store:{env['POSTGRES_PASSWORD']}@postgres:5432/accounts"
keys += ["DATABASE_URL"]
for key in keys:
    if not env.get(key) or (key != "DATABASE_URL" and len(env[key]) < 32):
        parser.error(f"Missing or short {key}")
secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "store-secrets", "namespace": "store"},
          "type": "Opaque", "data": {key: base64.b64encode(env[key].encode()).decode() for key in keys}}
subprocess.run(["kubectl", "--context", args.context, "apply", "-f", "-"], input=json.dumps(secret), text=True, check=True)
