"""Verify committed submodule structure using local source URLs before remote publication."""
from pathlib import Path
import argparse
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument("--destination",default="artifacts/clean-clone")
args=parser.parse_args()
clone=(root/args.destination).resolve()
if clone.exists():
    raise SystemExit("Destination already exists; choose a fresh --destination")
configured=subprocess.check_output(["git","config","-f",str(root/".gitmodules"),"--get-regexp",r"^submodule\..*\.path$"],text=True)
paths=[line.split(None,1)[1] for line in configured.splitlines()]
subprocess.run(["git","-c","protocol.file.allow=always","clone","--no-hardlinks",str(root),str(clone)],check=True)
for path in paths:
    subprocess.run(["git","-C",str(clone),"config",f"submodule.{path}.url",str(root/path)],check=True)
subprocess.run(["git","-C",str(clone),"-c","protocol.file.allow=always","submodule","update","--init","--recursive"],check=True)
for path in paths:
    expected=subprocess.check_output(["git","-C",str(root),"rev-parse",f"HEAD:{path}"],text=True).strip()
    actual=subprocess.check_output(["git","-C",str(clone/path),"rev-parse","HEAD"],text=True).strip()
    assert actual==expected,(path,expected,actual)
subprocess.run([sys.executable,"scripts/setup-local.py"],cwd=clone,check=True)
subprocess.run(["docker","compose","config","--quiet"],cwd=clone,check=True)
subprocess.run(["docker","compose","-f","compose.yaml","-f","compose.business.yaml","config","--quiet"],cwd=clone,check=True)
print(f"PASS: clean local clone restores all {len(paths)} pinned submodules and validates both Compose configurations")
print("Remote clone still requires publishing these commits to GitHub")
