"""Publish only explicit, non-secret integration evidence into the docs submodule."""
import json
from pathlib import Path
import subprocess

target=Path("docs/site/docs/evidence/2026-11-11")
target.mkdir(parents=True,exist_ok=True)
for source,name in [("business-integration-compose.json","compose.json"),("business-integration-k8s.json","kubernetes.json"),("business-resilience.json","resilience.json")]:
    data=json.loads((Path("artifacts")/source).read_text())
    (target/name).write_bytes(json.dumps(data,indent=2).encode("utf-8"))
for source,name in [("integration-cluster.txt","cluster.txt"),("integration-resources.txt","resources.txt")]:
    raw=(Path("artifacts")/source).read_bytes()
    decoded=raw.decode("utf-16") if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else raw.decode("utf-8-sig")
    clean="\n".join(line.rstrip() for line in decoded.splitlines())+"\n"
    (target/name).write_bytes(clean.encode("utf-8"))
services=["account","auth","gateway","product","order","exchange"]
revisions={s:subprocess.check_output(["git","-C","api/"+s,"rev-parse","HEAD"],text=True).strip() for s in services}
images={s:subprocess.check_output(["docker","image","inspect","microserv-store/"+s+":local","--format","{{.Id}}"],text=True).strip() for s in services}
(target/"revisions.json").write_bytes(json.dumps({"source_commits":revisions,"runtime_images":images,
  "note":"Local images are identified by digest. Registry publication and Jenkins deployment have not been claimed."},indent=2).encode("utf-8"))
print("Collected integration evidence:",target)
