"""Render immutable images and validate/apply to an explicitly selected cluster."""
import argparse
from pathlib import Path
import re
import subprocess
parser=argparse.ArgumentParser()
parser.add_argument("--context",required=True)
for service in ("account","auth","gateway"):
    parser.add_argument("--"+service+"-image",required=True)
for service in ("product","order","exchange"):
    parser.add_argument("--"+service+"-image")
parser.add_argument("--apply",action="store_true",help="Apply after successful server-side dry-run")
args=parser.parse_args()
services=["account","auth","gateway"]
if any(getattr(args,s+"_image") for s in ("product","order","exchange")):
    if not all(getattr(args,s+"_image") for s in ("product","order","exchange")):
        parser.error("Provide all three business images together")
    services += ["product","exchange","order"]
manifests=[]
for service in services:
    image=getattr(args,service+"_image")
    if not re.fullmatch(r"[a-z0-9][a-z0-9./_-]*:[a-f0-9]{40}",image):
        parser.error("Use a registry image with a full 40-character commit SHA tag")
    text=Path(f"api/{service}/k8s/k8s.yaml").read_text()
    manifests.append(text.replace(f"microserv-store/{service}:local",image))
rendered="\n---\n".join(manifests)
output=Path("artifacts/deployment.rendered.yaml");output.parent.mkdir(exist_ok=True)
output.write_text(rendered)
base=["kubectl","--context",args.context,"apply","-f",str(output)]
subprocess.run(base+["--dry-run=server"],check=True)
if args.apply:
    subprocess.run(base,check=True)
    for service in services:
        subprocess.run(["kubectl","--context",args.context,"-n","store","rollout","status",f"deployment/{service}","--timeout=180s"],check=True)
else:
    print("Validated rendered deployment; use --apply to deploy")
