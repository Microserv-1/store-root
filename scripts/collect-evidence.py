"""Copy an explicit allowlist of non-secret evidence into the documentation repo."""
import json
from pathlib import Path
import shutil
import subprocess

target=Path("docs/site/docs/evidence/2026-11-09")
target.mkdir(parents=True,exist_ok=True)
for name in ["compose-baseline-final.json","k8s-baseline-final.json","k8s-login-final.json",
             "k8s-balance-final.json","pod-recovery.json","recorded-hpa.json"]:
    data=json.loads((Path("artifacts")/name).read_text())
    (target/name).write_text(json.dumps(data,indent=2),encoding="utf-8")
shutil.copy2("artifacts/hpa-evidence.mp4",target/"hpa-local.mp4")
base=["kubectl","--context","kind-microserv-store","-n","store"]
for name,args in [("cluster",["get","deployments,pods,services,hpa","-o","wide"]),
                  ("resources",["top","pods"]),
                  ("events",["get","events","--sort-by=.lastTimestamp"])]:
    (target/(name+".txt")).write_text(subprocess.check_output(base+args,text=True),encoding="utf-8")
targets=json.loads(subprocess.check_output(base+["exec","deployment/prometheus","--","wget","-qO-","http://localhost:9090/api/v1/targets"],text=True))
(target/"prometheus-targets.json").write_text(json.dumps(targets,indent=2))
images={s:subprocess.check_output(["docker","image","inspect",f"microserv-store/{s}:local","--format","{{.Id}}"],text=True).strip() for s in ("account","auth","gateway")}
(target/"images.json").write_text(json.dumps(images,indent=2))
print("Saved sanitized local evidence to",target)
