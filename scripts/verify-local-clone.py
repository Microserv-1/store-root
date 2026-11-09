"""Verify committed submodule structure using local source URLs before remote publication."""
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
clone=root/"artifacts"/"clean-clone"
if clone.exists():
    raise SystemExit("artifacts/clean-clone already exists; choose a fresh checkout manually")
subprocess.run(["git","-c","protocol.file.allow=always","clone","--no-hardlinks",str(root),str(clone)],check=True)
for path in ("api/account","api/auth","api/gateway","docs/site"):
    subprocess.run(["git","-C",str(clone),"config",f"submodule.{path}.url",str(root/path)],check=True)
subprocess.run(["git","-C",str(clone),"-c","protocol.file.allow=always","submodule","update","--init","--recursive"],check=True)
for path in ("api/account","api/auth","api/gateway","docs/site"):
    expected=subprocess.check_output(["git","-C",str(root),"rev-parse",f"HEAD:{path}"],text=True).strip()
    actual=subprocess.check_output(["git","-C",str(clone/path),"rev-parse","HEAD"],text=True).strip()
    assert actual==expected,(path,expected,actual)
subprocess.run([sys.executable,"scripts/setup-local.py"],cwd=clone,check=True)
subprocess.run(["docker","compose","config","--quiet"],cwd=clone,check=True)
print("PASS: clean local clone restores all four pinned submodules and validates Compose")
print("Remote clone still requires publishing these commits to GitHub")
