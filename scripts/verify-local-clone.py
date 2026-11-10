"""Verify committed submodule structure using local source URLs before remote publication."""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
clone = root / "artifacts" / "clean-clone"
if clone.exists():
    shutil.rmtree(clone)

submodules = [
    "api/account",
    "api/auth",
    "api/gateway",
    "api/product",
    "api/order",
    "api/exchange",
    "docs/site",
]
if (root / "docs" / "site-b" / ".git").exists():
    submodules.append("docs/site-b")

subprocess.run(["git", "-c", "protocol.file.allow=always", "clone", "--no-hardlinks", str(root), str(clone)], check=True)
for path in submodules:
    subprocess.run(["git", "-C", str(clone), "config", f"submodule.{path}.url", str(root / path)], check=True)
subprocess.run(["git", "-C", str(clone), "-c", "protocol.file.allow=always", "submodule", "update", "--init", "--recursive"], check=True)
for path in submodules:
    expected = subprocess.check_output(["git", "-C", str(root), "rev-parse", f"HEAD:{path}"], text=True).strip()
    actual = subprocess.check_output(["git", "-C", str(clone / path), "rev-parse", "HEAD"], text=True).strip()
    assert actual == expected, (path, expected, actual)
subprocess.run([sys.executable, "scripts/setup-local.py"], cwd=clone, check=True)
subprocess.run(["docker", "compose", "config", "--quiet"], cwd=clone, check=True)
shutil.rmtree(clone)
print(f"PASS: clean local clone restores all {len(submodules)} pinned submodules and validates Compose")
