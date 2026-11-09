"""Create local secrets without overwriting an existing environment."""
from pathlib import Path
import secrets
root = Path(__file__).resolve().parents[1]
path = root / ".env"
if path.exists():
    print(".env already exists; preserved")
else:
    keys = ["JWT_SECRET", "INTERNAL_AUTH_KEY", "POSTGRES_PASSWORD", "GRAFANA_PASSWORD"]
    path.write_text("".join(f"{key}={secrets.token_hex(32)}\n" for key in keys) + "GATEWAY_PORT=8080\n")
    print("Created .env with random local secrets (ignored by Git)")
