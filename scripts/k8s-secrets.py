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
parser.add_argument("--business", action="store_true", help="Include Product/Order databases and broker/cache credentials")
args = parser.parse_args()
env = dict(line.split("=", 1) for line in Path(args.env_file).read_text().splitlines() if line and not line.startswith("#"))
keys = ["JWT_SECRET", "INTERNAL_AUTH_KEY", "GRAFANA_PASSWORD"]
if args.local_database:
    keys += ["POSTGRES_PASSWORD"]
    env["DATABASE_URL"] = f"postgresql+psycopg://store:{env['POSTGRES_PASSWORD']}@postgres:5432/accounts"
keys += ["DATABASE_URL"]
if args.business:
    keys += ["PRODUCT_DB_PASSWORD", "ORDER_DB_PASSWORD", "REDIS_PASSWORD", "RABBITMQ_PASSWORD"]
    if args.local_database:
        env["PRODUCT_DATABASE_URL"] = f"postgresql+psycopg://product:{env['PRODUCT_DB_PASSWORD']}@product-db:5432/products"
        env["ORDER_DATABASE_URL"] = f"postgresql+psycopg://orders:{env['ORDER_DB_PASSWORD']}@order-db:5432/orders"
        env["REDIS_URL"] = f"redis://:{env['REDIS_PASSWORD']}@redis:6379/0"
        env["RABBITMQ_URL"] = f"amqp://store:{env['RABBITMQ_PASSWORD']}@rabbitmq:5672/%2F"
    keys += ["PRODUCT_DATABASE_URL", "ORDER_DATABASE_URL", "REDIS_URL", "RABBITMQ_URL"]
for key in keys:
    if not env.get(key) or (not key.endswith("_URL") and len(env[key]) < 32):
        parser.error(f"Missing or short {key}")
secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "store-secrets", "namespace": "store"},
          "type": "Opaque", "data": {key: base64.b64encode(env[key].encode()).decode() for key in keys}}
subprocess.run(["kubectl", "--context", args.context, "apply", "-f", "-"], input=json.dumps(secret), text=True, check=True)
