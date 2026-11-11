"""Create local secrets without overwriting an existing environment."""
from pathlib import Path
import secrets
root = Path(__file__).resolve().parents[1]
path = root / ".env"
existing = path.read_text() if path.exists() else ""
present = {line.split("=",1)[0] for line in existing.splitlines() if "=" in line and not line.startswith("#")}
keys = ["JWT_SECRET", "INTERNAL_AUTH_KEY", "POSTGRES_PASSWORD", "GRAFANA_PASSWORD",
        "PRODUCT_DB_PASSWORD", "ORDER_DB_PASSWORD", "REDIS_PASSWORD", "RABBITMQ_PASSWORD"]
missing = [key for key in keys if key not in present]
if missing or "GATEWAY_PORT" not in present:
    additions = "".join(f"{key}={secrets.token_hex(32)}\n" for key in missing)
    if "GATEWAY_PORT" not in present:
        additions += "GATEWAY_PORT=8080\n"
    path.write_text(existing.rstrip()+"\n"+additions if existing else additions)
    print("Added missing local configuration; existing secrets preserved")
else:
    print("Local configuration complete; existing secrets preserved")
